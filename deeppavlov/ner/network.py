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

import os

from collections import defaultdict

import numpy as np
import tensorflow as tf
from .layers import character_embedding_network
from .layers import embedding_layer
from .layers import highway_convolutional_network
from .layers import stacked_convolutions
from .layers import stacked_rnn
from tensorflow.contrib.layers import xavier_initializer
from itertools import chain

from deeppavlov.core.tf_backend import TFModel


SEED = 42
MODEL_PATH = 'model/'
MODEL_FILE_NAME = 'ner_model'


class NerNetwork(TFModel):

    def __init__(self,
                 word_vocab,
                 char_vocab,
                 tag_vocab,
                 n_filters=(128, 256),
                 filter_width=3,
                 token_embeddings_dim=128,
                 char_embeddings_dim=50,
                 use_char_embeddins=True,
                 pretrained_model_filepath=None,
                 embeddings_dropout=False,
                 dense_dropout=False,
                 use_batch_norm=False,
                 logging=False,
                 entity_of_interest=None,
                 use_crf=False,
                 net_type='cnn',
                 char_filter_width=5,
                 verbouse=False,
                 embeddings_onethego=False):

        n_tags = len(tag_vocab)
        n_tokens = len(word_vocab)
        n_chars = len(char_vocab)

        self.tokens_vocab = word_vocab
        self.chars_vocab = char_vocab
        self.tags_vocab = tag_vocab

        # Create placeholders
        # noinspection PyPackageRequirements
        if embeddings_onethego:
            x_word = tf.placeholder(dtype=tf.float32, shape=[None, None, token_embeddings_dim], name='x_word')
        else:
            x_word = tf.placeholder(dtype=tf.int32, shape=[None, None], name='x_word')
        x_char = tf.placeholder(dtype=tf.int32, shape=[None, None, None], name='x_char')
        y_true = tf.placeholder(dtype=tf.int32, shape=[None, None], name='y_tag')

        # Auxiliary placeholders
        learning_rate_ph = tf.placeholder(dtype=tf.float32, shape=[], name='learning_rate')
        dropout_ph = tf.placeholder_with_default(1.0, shape=[])
        training_ph = tf.placeholder_with_default(False, shape=[])
        mask_ph = tf.placeholder(dtype=tf.float32, shape=[None, None])

        # Embeddings
        if not embeddings_onethego:
            with tf.variable_scope('Embeddings'):
                w_emb = embedding_layer(x_word, n_tokens=n_tokens, token_embedding_dim=token_embeddings_dim)
                if use_char_embeddins:
                    c_emb = character_embedding_network(x_char,
                                                        n_characters=n_chars,
                                                        char_embedding_dim=char_embeddings_dim,
                                                        filter_width=char_filter_width)
                    emb = tf.concat([w_emb, c_emb], axis=-1)
                else:
                    emb = w_emb
        else:
            emb = x_word

        # Dropout for embeddings
        if embeddings_dropout:
            emb = tf.layers.dropout(emb, dropout_ph, training=training_ph)

        if 'cnn' in net_type.lower():
            # Convolutional network
            with tf.variable_scope('ConvNet'):
                units = stacked_convolutions(emb,
                                             n_filters=n_filters,
                                             filter_width=filter_width,
                                             use_batch_norm=use_batch_norm,
                                             training_ph=training_ph)
        elif 'rnn' in net_type.lower():
            units = stacked_rnn(emb, n_filters, cell_type='lstm')

        elif 'cnn_highway' in net_type.lower():
            units = highway_convolutional_network(emb,
                                                  n_filters=n_filters,
                                                  filter_width=filter_width,
                                                  use_batch_norm=use_batch_norm,
                                                  training_ph=training_ph)
        else:
            raise KeyError('There is no such type of network: {}'.format(net_type))
        # Classifier
        with tf.variable_scope('Classifier'):
            logits = tf.layers.dense(units, n_tags, kernel_initializer=xavier_initializer())

        # Loss with masking
        if use_crf:
            sequence_lengths = tf.reduce_sum(mask_ph, axis=1)
            log_likelihood, trainsition_params = tf.contrib.crf.crf_log_likelihood(logits,
                                                                                   y_true,
                                                                                   sequence_lengths)
            loss_tensor = -log_likelihood
            predictions = None
        else:
            ground_truth_labels = tf.one_hot(y_true, n_tags)
            loss_tensor = tf.nn.softmax_cross_entropy_with_logits(labels=ground_truth_labels, logits=logits)
            loss_tensor = loss_tensor * mask_ph
            predictions = tf.argmax(logits, axis=-1)

        loss = tf.reduce_mean(loss_tensor)
        # Initialize session
        sess = tf.Session()
        if verbouse:
            self.print_number_of_parameters()
        if logging:
            self.train_writer = tf.summary.FileWriter('summary', sess.graph)

        self._use_crf = use_crf
        self.summary = tf.summary.merge_all()
        self._x_w = x_word
        self._x_c = x_char
        self._y_true = y_true
        self._y_pred = predictions
        if use_crf:
            self._logits = logits
            self._trainsition_params = trainsition_params
            self._sequence_lengths = sequence_lengths
        self._loss = loss
        self._sess = sess
        self._learning_rate_ph = learning_rate_ph
        self._dropout = dropout_ph
        self._loss_tensor = loss_tensor
        self._use_dropout = True if embeddings_dropout or dense_dropout else None
        self._training_ph = training_ph
        self._logging = logging
        self._train_op = self.get_train_op(loss, learning_rate_ph)
        self._embeddings_onethego = embeddings_onethego
        self._entity_of_interest = entity_of_interest
        self.verbouse = verbouse
        self._mask = mask_ph
        sess.run(tf.global_variables_initializer())
        if pretrained_model_filepath is not None:
            self.load(pretrained_model_filepath)

        self._is_network_initialized = True

    def save(self, model_file_path=None):
        if model_file_path is None:
            if not os.path.exists(MODEL_PATH):
                os.mkdir(MODEL_PATH)
            model_file_path = os.path.join(MODEL_PATH, MODEL_FILE_NAME)
        saver = tf.train.Saver()
        saver.save(self._sess, model_file_path)

    def load(self, model_file_path):
        saver = tf.train.Saver()
        saver.restore(self._sess, model_file_path)

    def infer(self, tokens_batch, chars_batch):
        tokens_idxs_batch = self.tokens_vocab.process(tokens_batch)
        char_idxs_batch = self.chars_vocab.process(chars_batch)
        prediction_batch = self.predict_on_batch(tokens_idxs_batch, char_idxs_batch)
        if prediction_batch is not None:
            result_batch = self.tags_vocab.batch_idxs2batch_toks(prediction_batch)
        else:
            result_batch = None
        return result_batch

    def _prepare_batch(self, tokens_idxs_batch, char_idxs_batch, tags_idxs_batch):
        batch_size = len(tokens_idxs_batch)

        max_utterance_len = max(len(utt) for utt in tokens_idxs_batch)

        if max_utterance_len == 0:
            return None, None, None, None

        max_token_len = max(len(token) for token in list(chain(*char_idxs_batch)))

        tokens_batch_np = np.zeros([batch_size, max_utterance_len], dtype=np.int32)
        tags_batch_np = np.zeros([batch_size, max_utterance_len], dtype=np.int32)
        mask_np = np.zeros([batch_size, max_utterance_len], dtype=np.int32)
        chars_batch_np = np.zeros([batch_size, max_utterance_len, max_token_len], dtype=np.int32)
        for n in range(batch_size):
            tokens_idxs = tokens_idxs_batch[n]
            if tags_idxs_batch is not None:
                tags_idxs = tags_idxs_batch[n]
            tokens_batch_np[n, :len(tokens_idxs)] = tokens_idxs
            mask_np[n, :len(tokens_idxs)] = 1
            if tags_idxs_batch is not None:
                tags_batch_np[n, :len(tags_idxs)] = tags_idxs
            for k in range(len(tokens_idxs)):
                characters = char_idxs_batch[n][k]
                chars_batch_np[n, k, :len(characters)] = characters
        return tokens_batch_np, chars_batch_np, mask_np, tags_batch_np

    def train_on_batch(self, tokens_batch, chars_batch, tags_batch):
        tokens_idxs_batch = self.tokens_vocab.process(tokens_batch)
        char_idxs_batch = self.chars_vocab.process(chars_batch)
        tags_idxs_batch = self.chars_vocab.process(tags_batch)

        tokens_batch_np, chars_batch_np, mask_np, tags_batch_np = self._prepare_batch(tokens_idxs_batch, char_idxs_batch, tags_idxs_batch)
        if tokens_batch_np is None:
            return None
        loss = self.train(tokens_batch_np, chars_batch_np, mask_np, tags_batch_np)
        return loss

    def train(self, x_word, x_char, mask, y_tag, learning_rate=1e-3, dropout_rate=0.5):
        feed_dict = self._fill_feed_dict(x_word,
                                         x_char,
                                         mask,
                                         y_tag,
                                         learning_rate,
                                         dropout_rate=dropout_rate,
                                         training=True)
        loss, _ = self._sess.run([self._loss, self._train_op], feed_dict=feed_dict)
        return loss

    @staticmethod
    def print_number_of_parameters():
        print('Number of parameters: ')
        vars = tf.trainable_variables()
        blocks = defaultdict(int)
        for var in vars:
            # Get the top level scope name of variable
            block_name = var.name.split('/')[0]
            number_of_parameters = np.prod(var.get_shape().as_list())
            blocks[block_name] += number_of_parameters
        for block_name in blocks:
            print(block_name, blocks[block_name])
        total_num_parameters = np.sum(list(blocks.values()))
        print('Total number of parameters equal {}'.format(total_num_parameters))

    def fit(self, batch_gen=None, batch_size=32, learning_rate=1e-3, epochs=1, dropout_rate=0.5, learning_rate_decay=1):
        for epoch in range(epochs):
            count = 0
            if self.verbouse:
                print('Epoch {}'.format(epoch))
            if batch_gen is None:
                batch_generator = self.corpus.batch_generator(batch_size, dataset_type='train')
            for (x_word, x_char), y_tag in batch_generator:

                feed_dict = self._fill_feed_dict(x_word,
                                                 x_char,
                                                 y_tag,
                                                 learning_rate,
                                                 dropout_rate=dropout_rate,
                                                 training=True)
                if self._logging:
                    summary, _ = self._sess.run([self.summary, self._train_op], feed_dict=feed_dict)
                    self.train_writer.add_summary(summary)

                self._sess.run(self._train_op, feed_dict=feed_dict)
                count += len(x_word)
            if self.verbouse:
                self.eval_conll('valid', print_results=True)
            self.save()

        if self.verbouse:
            self.eval_conll(dataset_type='train', short_report=False)
            self.eval_conll(dataset_type='valid', short_report=False)
            results = self.eval_conll(dataset_type='test', short_report=False)
        else:
            results = self.eval_conll(dataset_type='test', short_report=True)
        return results

    def predict_on_batch(self, tokens_idxs_batch, char_idxs_batch):
        tokens_batch_np, chars_batch_np, mask_np, tags_batch_np = self._prepare_batch(tokens_idxs_batch, char_idxs_batch, None)
        if tokens_batch_np is None:
            return None
        prediction = self.predict(tokens_batch_np, chars_batch_np)
        return prediction

    def predict(self, x_word, x_char):
        feed_dict = self._fill_feed_dict(x_word, x_char, training=False)
        if self._use_crf:
            y_pred = []
            logits, trans_params, sequence_lengths = self._sess.run([self._logits,
                                                                     self._trainsition_params,
                                                                     self._sequence_lengths
                                                                     ],
                                                                    feed_dict=feed_dict)

            # iterate over the sentences because no batching in viterbi_decode
            for logit, sequence_length in zip(logits, sequence_lengths):
                logit = logit[:int(sequence_length)]  # keep only the valid steps
                viterbi_seq, viterbi_score = tf.contrib.crf.viterbi_decode(logit, trans_params)
                y_pred += [viterbi_seq]
        else:
            y_pred = self._sess.run(self._y_pred, feed_dict=feed_dict)
        return y_pred

    def _fill_feed_dict(self,
                        x_w,
                        x_c,
                        mask=None,
                        y_t=None,
                        learning_rate=None,
                        training=False,
                        dropout_rate=1):
        feed_dict = dict()
        feed_dict[self._x_w] = x_w
        feed_dict[self._x_c] = x_c
        feed_dict[self._training_ph] = training
        if mask is not None:
            feed_dict[self._mask] = mask
        else:
            feed_dict[self._mask] = np.ones(x_w.shape[:2])
        if y_t is not None:
            feed_dict[self._y_true] = y_t
        if learning_rate is not None:
            feed_dict[self._learning_rate_ph] = learning_rate
        if self._use_dropout is not None and training:
            feed_dict[self._dropout] = dropout_rate
        else:
            feed_dict[self._dropout] = 1.0
        return feed_dict

    def eval_loss(self, data_generator):
        num_tokens = 0
        loss = 0
        for (x_w, x_c), y_t in data_generator:
            feed_dict = self._fill_feed_dict(x_w, x_c, y_t, training=False)
            loss += np.sum(self._sess.run(self._loss_tensor, feed_dict=feed_dict))
            num_tokens = np.sum(self._sess.run(self._sequence_lengths, feed_dict=feed_dict))
        return loss / num_tokens

    @staticmethod
    def get_trainable_variables(trainable_scope_names=None):
        vars = tf.trainable_variables()
        if trainable_scope_names is not None:
            vars_to_train = list()
            for scope_name in trainable_scope_names:
                for var in vars:
                    if var.name.startswith(scope_name):
                        vars_to_train.append(var)
            return vars_to_train
        else:
            return vars

    def get_train_op(self, loss, learning_rate, learnable_scopes=None):
        variables = self.get_trainable_variables(learnable_scopes)

        # For batch norm it is necessary to update running averages
        extra_update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
        with tf.control_dependencies(extra_update_ops):
            train_op = tf.train.AdamOptimizer(learning_rate).minimize(loss, var_list=variables)
        return train_op

    def shutdown(self):
        pass
        # self._sess.close()
        # tf.reset_default_graph()