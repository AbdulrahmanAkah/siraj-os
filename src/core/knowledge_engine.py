from core.repositories.entity_repository import EntityRepository
from core.entities import Entity


class KnowledgeEngine:
    def __init__(self):
        self.entities = EntityRepository()

    def register(self, entity: Entity):
        self.entities.add(entity)

    def find(self, entity_id: str):
        return self.entities.get(entity_id)

    def all_entities(self):
        return self.entities.all()

    def stats(self):
        return {
            "entities": self.entities.count()
        }