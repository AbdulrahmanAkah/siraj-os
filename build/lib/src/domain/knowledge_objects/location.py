from dataclasses import dataclass, field
from src.domain.knowledge_objects.source_reference import SourceReference
from src.domain.knowledge_objects.knowledge_object import KnowledgeObject

@dataclass
class Location(KnowledgeObject):
    name:str=""
    description:str=""
    source_reference:SourceReference|None=None


