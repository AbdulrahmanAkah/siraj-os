from .text_normalizer import TextNormalizer


class RelationshipNormalizer:

    def __init__(self):
        self.text = TextNormalizer()

    def normalize(self, extraction):

        for r in extraction.relationships:

            r.subject = self.text.normalize(r.subject)
            r.object = self.text.normalize(r.object)
            r.predicate = self.text.normalize(r.predicate)

        return extraction


