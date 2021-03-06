from deeppavlov.core.components import Component
from deeppavlov.core.registrable import Registrable

from overrides import overrides

import logging


logger = logging.getLogger(__name__)


@Registrable.register("hcn")
class HcnComponent(Component):

    def __init__(self, config):
        super().__init__(config)
        self.local_input_names = ['bow', 'emb', 'entities', 'classes', 'response', 'other']
        self.local_output_names = ['result']

        self._is_network_initialized = False

        self.hcn = None

    @overrides
    def setup(self, components={}):
        super().setup(components)
        self.hcn = HybridCodeNetworkBot(self.config)
        self.load()

    @overrides
    def save(self):
        if "save_to" in self.config:
            path = self.config["save_to"]
            # self.network.save(path)

    @overrides
    def load(self):
        if "load" in self.config:
            path = self.config["load"]
            # self.network.load(path)

    @overrides
    def forward(self, smem, add_local_mem=False):
        bow = self.get_input("bow", smem)

        emb = self.get_input("emb", smem)

        entities = self.get_input("entities", smem)

        classes = self.get_input("classes", smem)

        result = self.hcn.infer_on_batch(bow, emb, entities, classes)

        self.set_output("result", result, smem)

    @overrides
    def train(self, smem, add_local_mem=False):

        bow = self.get_input("bow", smem)

        emb = self.get_input("emb", smem)

        entities = self.get_input("entities", smem)

        classes = self.get_input("classes", smem)

        response = self.get_input("response", smem)

        other = self.get_input("other", smem)

        # logger.debug("BOW: %s" % bow)
        # logger.debug("EMB: %s" % emb)
        # logger.debug("Entities: %s" % entities)

        loss = self.hcn.train_on_batch(bow, emb, entities, classes, response, other)

        self.set_output("result", loss, smem)
        logger.debug("Loss %s" % loss)

    @overrides
    def shutdown(self):
        pass
        # self.network.shutdown()

"""
Copyright 2017 Neural Networks and Deep Learning lab, MIPT
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at
    http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import re

import numpy as np

from deeppavlov.skills.tracker import FeaturizedTracker
from deeppavlov.skills.metrics import DialogMetrics
from deeppavlov.skills.network import HybridCodeNetworkModel
from deeppavlov.skills.templates import Templates, DualTemplate


class HybridCodeNetworkBot:
    def __init__(self,
                 config,
                 # template_path,
                 # template_type: Type = DualTemplate,
                 # slot_filler: Type = DstcSlotFillingNetwork,
                 # intent_classifier:Type = KerasIntentModel,
                 # bow_encoder: Type = BoW_encoder,
                 # embedder: Type = FasttextEmbedder,
                 # tokenizer: Type = SpacyTokenizer,
                 # tracker: Type = DefaultTracker,
                 # network: Type = HybridCodeNetworkModel,
                 # word_vocab: Type = DefaultVocabulary,
                 vocab_path=None,
                 use_action_mask=False,
                 debug=False,
                 num_epochs=100,
                 val_patience=5):

        self.episode_done = True
        self.use_action_mask = config["use_action_mask"]
        self.debug = debug
        # self.slot_filler = slot_filler
        # self.intent_classifier = intent_classifier
        # self.bow_encoder = bow_encoder
        # self.embedder = embedder
        # self.tokenizer = tokenizer
        self.tracker = FeaturizedTracker(config["slot_names"])
        self.network = HybridCodeNetworkModel(config)
        # self.word_vocab = word_vocab
        self.num_epochs = num_epochs
        self.val_patience = val_patience

        self.templates = Templates(DualTemplate).load(config["template_path"])
        print("[using {} templates from `{}`]" \
              .format(len(self.templates), config["template_path"]))

        # intialize parameters
        self.db_result = None
        self.n_actions = len(self.templates)
        self.n_intents = int(config["intents_size"]) # len(self.intent_classifier.infer(['hi']))
        self.prev_action = np.zeros(self.n_actions, dtype=np.float32)

        # initialize metrics
        self.metrics = DialogMetrics(self.n_actions)

        # opt = {
        #    'action_size': self.n_actions,
        #    'obs_size': 4 + len(self.word_vocab) + self.embedder.dim +\
        #    2 * self.tracker.state_size + self.n_actions + self.n_intents
        #}
        #self.network = HybridCodeNetworkModel(opt)

    def _encode_context(self, bow, emb, entities, classes, db_result=None):
        # # tokenize input
        # tokenized = ' '.join(self.tokenizer.infer(context)).strip()
        # if self.debug:
        #     print("Text tokens = `{}`".format(tokenized))
        #
        # # Bag of words features
        # bow_features = self.bow_encoder.infer(tokenized, self.word_vocab)
        # bow_features = bow_features.astype(np.float32)
        #
        # # Embeddings
        # emb_features = self.embedder.infer(tokenized, mean=True)
        #
        # # Intent features
        # intent_features = self.intent_classifier.infer([tokenized]).ravel()
        # if self.debug:
        #     from deeppavlov.models.classifiers.intents.utils import proba2labels
        #     print("Predicted intent = `{}`".format(proba2labels(
        #         intent_features[np.newaxis, :], .5, self.intent_classifier.classes
        #     )[0]))

        # Text entity features
        self.tracker.update_state(entities)
        state_features = self.tracker.infer()
        if self.debug:
            print("Found slots =", entities)

        # Other features
        context_features = np.array([(db_result == {}) * 1.,
                                     (self.db_result == {}) * 1.],
                                    dtype=np.float32)

        if self.debug:
            print("num bow features =", len(bow),
                  " num emb features =", len(emb),
                  " num intent features =", len(classes),
                  " num state features =", len(state_features),
                  " num context features =", len(context_features),
                  " prev_action shape =", len(self.prev_action))

        classes = classes[0] if len(classes.shape) == 2 else classes

        return np.hstack((bow, emb, classes, state_features, context_features, self.prev_action))[np.newaxis, :]

    def _encode_response(self, response, act):
        return self.templates.actions.index(act)

    def _decode_response(self, action_id):
        """
        Convert action template id and entities from tracker
        to final response.
        """
        template = self.templates.templates[int(action_id)]

        slots = self.tracker.get_state()
        if self.db_result is not None:
            for k, v in self.db_result.items():
                slots[k] = str(v)

        return template.generate_text(slots)

    def _action_mask(self):
        action_mask = np.ones(self.n_actions, dtype=np.float32)
        if self.use_action_mask:
            # TODO: non-ones action mask
            for a_id in range(self.n_actions):
                tmpl = str(self.templates.templates[a_id])
                for entity in re.findall('#{}', tmpl):
                    if entity not in self.tracker.get_state() \
                            and entity not in (self.db_result or {}):
                        action_mask[a_id] = 0
        return action_mask

    def train_on_batch(self, bow, emb, entities, classes, response, other):
        if other.get('episode_done'):
            self.reset()
            self.metrics.n_dialogs += 1

        if other.get('db_result') is not None:
            self.db_result = other['db_result']
        action_id = self._encode_response(response, other['act'])

        loss, pred_id = self.network._train_step(
            self._encode_context(bow, emb, entities, classes, other.get('db_result')),
            action_id,
            self._action_mask()
        )

        self.prev_action *= 0.
        self.prev_action[pred_id] = 1.

        return loss

        # pred = self._decode_response(pred_id).lower()
        # true = self.tokenizer.infer(response.lower().split())

        # update metrics
        # self.metrics.n_examples += 1
        # self.metrics.train_loss += loss
        # self.metrics.conf_matrix[pred_id, action_id] += 1
        # self.metrics.n_corr_examples += int(pred == true)
        # if self.debug and ((pred == true) != (pred_id == action_id)):
        #     print("Slot filling problem: ")
        #     print("Pred = {}: {}".format(pred_id, pred))
        #     print("True = {}: {}".format(action_id, true))
        #     print("State =", self.tracker.get_state())
        #     print("db_result =", self.db_result)

    def train(self, data):
        print('\n:: training started')

        curr_patience = self.val_patience
        prev_valid_accuracy = 0.
# TODO: in case val_patience is off, save model {val_patience} steps before
        for j in range(self.num_epochs):

            tr_data = data.iter_all('train')
            eval_data = data.iter_all('valid')

            self.reset_metrics()

            for context, response, other in tr_data:
                if other.get('episode_done'):
                    self.reset()
                    self.metrics.n_dialogs += 1

                if other.get('db_result') is not None:
                    self.db_result = other['db_result']
                action_id = self._encode_response(response, other['act'])

                loss, pred_id = self.network.train(
                    self._encode_context(context, other.get('db_result')),
                    action_id,
                    self._action_mask()
                )

                self.prev_action *= 0.
                self.prev_action[pred_id] = 1.

                pred = self._decode_response(pred_id).lower()
                true = self.tokenizer.infer(response.lower().split())

                # update metrics
                self.metrics.n_examples += 1
                self.metrics.train_loss += loss
                self.metrics.conf_matrix[pred_id, action_id] += 1
                self.metrics.n_corr_examples += int(pred == true)
                if self.debug and ((pred == true) != (pred_id == action_id)):
                    print("Slot filling problem: ")
                    print("Pred = {}: {}".format(pred_id, pred))
                    print("True = {}: {}".format(action_id, true))
                    print("State =", self.tracker.get_state())
                    print("db_result =", self.db_result)
                    # TODO: update dialog metrics
            print('\n\n:: {}.train {}'.format(j + 1, self.metrics.report()))

            valid_metrics = self.evaluate(eval_data)
            print(':: {}.valid {}'.format(j + 1, valid_metrics.report()))

            if prev_valid_accuracy > valid_metrics.action_accuracy:
                curr_patience -= 1
                print(":: patience decreased by 1, is equal to {}".format(curr_patience))
            else:
                curr_patience = self.val_patience
            if curr_patience < 1:
                print("\n:: patience is over, stopped training\n")
                break
            prev_valid_accuracy = valid_metrics.action_accuracy
        else:
            print("\n:: stopping because max number of epochs encountered\n")
        self.save()

    def infer_on_batch(self, bow, emb, entities, classes, db_result=None):
        if db_result is not None:
            self.db_result = db_result
        probs, pred_id = self.network._forward(
            self._encode_context(bow, emb, entities, classes, db_result),
            self._action_mask()
        )
        self.prev_action *= 0.
        self.prev_action[pred_id] = 1.
        return pred_id

    def infer(self, context, db_result=None):
        if db_result is not None:
            self.db_result = db_result
        probs, pred_id = self.network.infer(
            self._encode_context(context, db_result),
            self._action_mask()
        )
        self.prev_action *= 0.
        self.prev_action[pred_id] = 1.
        return self._decode_response(pred_id)

    def evaluate(self, eval_data):
        metrics = DialogMetrics(self.n_actions)

        for context, response, other in eval_data:

            if other.get('episode_done'):
                self.reset()
                metrics.n_dialogs += 1

            if other.get('db_result') is not None:
                self.db_result = other['db_result']

            probs, pred_id = self.network.infer(
                self._encode_context(context, other.get('db_result')),
                self._action_mask()
            )

            self.prev_action *= 0.
            self.prev_action[pred_id] = 1.

            pred = self._decode_response(pred_id).lower()
            true = self.tokenizer.infer(response.lower().split())

            # update metrics
            metrics.n_examples += 1
            action_id = self._encode_response(response, other['act'])
            metrics.conf_matrix[pred_id, action_id] += 1
            metrics.n_corr_examples += int(pred == true)
        return metrics

    def reset(self):
        self.tracker.reset_state()
        self.db_result = None
        self.prev_action = np.zeros(self.n_actions, dtype=np.float32)
        self.network.reset_state()

    def report(self):
        return self.metrics.report()

    def reset_metrics(self):
        self.metrics.reset()

    def save(self):
        """Save the parameters of the model to a file."""
        self.network.save()

    def shutdown(self):
        self.network.shutdown()
        # self.slot_filler.shutdown()

    def load(self):
        pass