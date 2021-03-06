from deeppavlov.testing.test_case import DPTestCase
from deeppavlov.data.dstc2 import DSTC2Reader, DSTC2NerProvider, DSTC2DialogProvider, DSTC2IntentsProvider
from deeppavlov.core.registrable import Registrable


class TestDSTC2(DPTestCase):

    def test_dstc2reader(self):
        data = DSTC2Reader.read(data_path=self.TEST_DIR)
        assert "train" in data
        assert len(data["train"]) == 967

        sample = data["train"][0]

        assert 7 == len(sample)

        assert sample[0] == {
            'context': {
                'text': '',
                'intents': [],
                'db_result': None
            },
            'response': {
                'text': 'Hello, welcome to the Cambridge restaurant system. You can ask for restaurants by area, price range or food type. How may I help you?',
                'act': 'welcomemsg'
            }
        }

    def test_dstc2_ner_dataset(self):
        ds = Registrable.by_name("provider.ner.dstc2")
        self.assertIsInstance(ds, DSTC2NerProvider.__class__)

    def test_dstc2_dialog_dataset(self):
        ds = Registrable.by_name("provider.dialog.dstc2")
        self.assertIsInstance(ds, DSTC2DialogProvider.__class__)

    def test_dstc2_intent_dataset(self):
        ds = Registrable.by_name("provider.intents.dstc2")
        self.assertIsInstance(ds, DSTC2IntentsProvider.__class__)

    def test_dstc2_ner_provider(self):
        data = DSTC2Reader.read(data_path=self.TEST_DIR)
        provider = DSTC2NerProvider(data, 1)
        batches = provider.batch_generator(10)
        batch = next(batches)
        assert batch == {
            'tokens': (['airatarin'], ['thank', 'you', 'good', 'bye'], [], [], ['restaurant'], ['thank', 'you', 'good', 'bye'], [], [], ['what', 'about', 'any', 'area'], ['im', 'looking', 'for', 'an', 'expensive', 'restaurant', 'in', 'the', 'east', 'part', 'of', 'town']),
            'tags': (['O'], ['O', 'O', 'O', 'O'], [], [], ['O'], ['O', 'O', 'O', 'O'], [], [], ['O', 'O', 'O', 'O'], ['O', 'O', 'O', 'O', 'B-pricerange', 'O', 'O', 'O', 'B-area', 'O', 'O', 'O'])
        }

    def test_dstc2_dialog_provider(self):
        data = DSTC2Reader.read(data_path=self.TEST_DIR)
        provider = DSTC2DialogProvider(data, 1)
        batches = provider.batch_generator(10)
        batch = next(batches)
        assert batch == {
            "text": '',
            "response": 'Hello, welcome to the Cambridge restaurant system. You can ask for restaurants by area, price range or food type. How may I help you?',
            "other": {'act': 'welcomemsg', 'episode_done': True}
        }

    def test_dstc2_intents_provider(self):
        data = DSTC2Reader.read(data_path=self.TEST_DIR)
        provider = DSTC2IntentsProvider(data, 1)
        batches = provider.batch_generator(1)
        batch = next(batches)
        assert batch == {
            "text": ['cantonese food'],
            "intents": [['inform_food']]
        }

