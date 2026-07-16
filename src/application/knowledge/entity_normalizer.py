from .name_normalizer import NameNormalizer
from .text_normalizer import TextNormalizer


class EntityNormalizer:

    def __init__(self):

        self.names = NameNormalizer()
        self.text = TextNormalizer()

    def normalize(self, extraction):

        for p in extraction.persons:
            p.name = self.names.normalize(p.name)

        for e in extraction.events:
            e.name = self.text.normalize(e.name)

        for l in extraction.locations:
            l.name = self.text.normalize(l.name)

        return extraction


