from typing import Dict, Optional
from core.entities import Entity


class EntityRepository:
    def __init__(self):
        self._entities: Dict[str, Entity] = {}

    def add(self, entity: Entity):
        self._entities[entity.entity_id] = entity

    def get(self, entity_id: str) -> Optional[Entity]:
        return self._entities.get(entity_id)

    def all(self):
        return list(self._entities.values())

    def count(self):
        return len(self._entities)