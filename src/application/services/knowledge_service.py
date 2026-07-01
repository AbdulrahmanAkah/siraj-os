from typing import List


class KnowledgeService:
    def __init__(self) -> None:
        self._entities: List[object] = []

    def register(self, entity: object) -> None:
        self._entities.append(entity)

    def all_entities(self) -> List[object]:
        return list(self._entities)

    def stats(self) -> str:
        return f"Registered entities: {len(self._entities)}"
