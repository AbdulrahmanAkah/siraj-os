from .entity_normalizer import EntityNormalizer
from .relationship_normalizer import RelationshipNormalizer


class GraphNormalizer:

    def __init__(self):

        self.entities = EntityNormalizer()
        self.relationships = RelationshipNormalizer()

    def normalize(self, extraction):

        extraction = self.entities.normalize(extraction)
        extraction = self.relationships.normalize(extraction)

        return extraction


