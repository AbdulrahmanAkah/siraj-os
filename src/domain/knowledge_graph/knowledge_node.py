from dataclasses import dataclass, field


@dataclass
class KnowledgeNode:
    id: str
    type: str
    data: dict[str, object]
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "type": self.type,
            "data": self.data,
            "metadata": self.metadata,
        }


__all__ = ["KnowledgeNode"]


