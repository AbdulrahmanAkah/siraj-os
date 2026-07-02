from dataclasses import dataclass, field
from typing import Dict, List, Optional
from uuid import uuid4


@dataclass
class Claim:
    claim_id: str = field(default_factory=lambda: str(uuid4()))
    text: str = ""
    language: str = "ar"
    status: str = "draft"
    confidence: float = 1.0
    entities: List["Entity"] = field(default_factory=list)
    sources: List["Source"] = field(default_factory=list)
    metadata: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "claim_id": self.claim_id,
            "text": self.text,
            "language": self.language,
            "status": self.status,
            "confidence": self.confidence,
            "entities": [
                item.to_dict() if hasattr(item, "to_dict") and callable(item.to_dict) else item
                for item in self.entities
            ],
            "sources": [
                item.to_dict() if hasattr(item, "to_dict") and callable(item.to_dict) else item
                for item in self.sources
            ],
            "metadata": self.metadata,
        }


__all__ = ["Claim"]
