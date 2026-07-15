from dataclasses import dataclass, field
from src.domain.knowledge_objects.knowledge_object_type import KnowledgeObjectType


@dataclass
class ExtractionObject:
    object_type: KnowledgeObjectType = KnowledgeObjectType.EVENT
    value: dict[str, object] = field(default_factory=dict)
    confidence: float = 1.0
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "object_type": self.object_type.value,
            "value": self.value,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


__all__ = ["ExtractionObject"]

