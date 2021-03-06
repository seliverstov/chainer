from deeppavlov.core.components import Component
from deeppavlov.core.registrable import Registrable
from deeppavlov.ner.network import NerNetwork

from overrides import overrides

import logging


logger = logging.getLogger(__name__)


@Registrable.register("ner")
class NerComponent(Component):

    def __init__(self, config):
        super().__init__(config)
        self.local_input_names = ['tokens', 'chars', 'tags']
        self.local_output_names = ['result']

        self.tokens_vocab_name = "tokens_vocab"
        self.chars_vocab_name = "chars_vocab"
        self.tags_vocab_name = "tags_vocab"

        self._is_network_initialized = False

        self.network = None

    @overrides
    def setup(self, components={}):
        super().setup(components)
        if self.network is None:
            self.network = NerNetwork(self._setup[self.tokens_vocab_name].vocab, self._setup[self.chars_vocab_name].vocab,
                               self._setup[self.tags_vocab_name].vocab)
            self.load()

    @overrides
    def save(self):
        if "save_to" in self.config:
            path = self.config["save_to"]
            self.network.save(path)

    @overrides
    def load(self):
        if "load" in self.config:
            path = self.config["load"]
            self.network.load(path)

    @overrides
    def forward(self, smem, add_local_mem=False):
        tokens = self.get_input("tokens", smem)
        chars = self.get_input("chars", smem)

        prediction = self.network.infer([tokens], [chars])

        self.set_output("result", prediction, smem)

    @overrides
    def train(self, smem, add_local_mem=False):

        tokens_batch = self.get_input("tokens", smem)

        chars_batch = self.get_input("chars", smem)

        tags_batch = self.get_input("tags", smem)

        loss = self.network.train_on_batch(tokens_batch, chars_batch, tags_batch)

        self.set_output("result", loss, smem)
        logger.debug("Loss %s" % loss)

    @overrides
    def shutdown(self):
        self.network.shutdown()