from dataclasses import dataclass, field

from src.domain.knowledge_objects.knowledge_object import KnowledgeObject


@dataclass
class Claim(KnowledgeObject):
    text: str = ""
    claim_id: str = ""
    source_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    confidence: float = 1.0


__all__ = ["Claim"]
