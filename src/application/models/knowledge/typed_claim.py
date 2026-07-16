from dataclasses import dataclass, field


@dataclass
class TypedClaim:
    claim: str = ""
    knowledge_type: str = "UNKNOWN"
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "claim": self.claim,
            "knowledge_type": self.knowledge_type,
            "metadata": self.metadata,
        }


__all__ = ["TypedClaim"]


