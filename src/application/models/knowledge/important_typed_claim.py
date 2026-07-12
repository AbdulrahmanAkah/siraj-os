from dataclasses import dataclass, field


@dataclass
class ImportantTypedClaim:
    claim: str = ""
    knowledge_type: str = "UNKNOWN"
    importance: str = "LOW"
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "claim": self.claim,
            "knowledge_type": self.knowledge_type,
            "importance": self.importance,
            "metadata": self.metadata,
        }


__all__ = ["ImportantTypedClaim"]


