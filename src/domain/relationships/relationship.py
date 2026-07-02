from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass
class Relationship:
    relationship_id: UUID = field(default_factory=uuid4)
    subject: str = ""
    predicate: str = ""
    object: str = ""
    confidence: float = 1.0
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "relationship_id": str(self.relationship_id),
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


__all__ = ["Relationship"]
