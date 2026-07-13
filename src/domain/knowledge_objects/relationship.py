from dataclasses import dataclass

from src.domain.knowledge_objects.knowledge_object import KnowledgeObject


@dataclass
class Relationship(KnowledgeObject):
    subject: str = ""
    predicate: str = ""
    object: str = ""


__all__ = ["Relationship"]
