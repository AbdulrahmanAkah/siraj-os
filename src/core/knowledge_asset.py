from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List
from uuid import UUID, uuid4


@dataclass
class KnowledgeAsset:
    asset_id: UUID = field(default_factory=uuid4)
    title: str = ""
    description: str = ""
    topic: str = ""
    language: str = "ar"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    status: str = "draft"
    entities: List["Entity"] = field(default_factory=list)
    claims: List["Claim"] = field(default_factory=list)
    sources: List["Source"] = field(default_factory=list)
    metadata: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "asset_id": str(self.asset_id),
            "title": self.title,
            "description": self.description,
            "topic": self.topic,
            "language": self.language,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "status": self.status,
            "entities": [
                item.to_dict() if hasattr(item, "to_dict") and callable(item.to_dict) else item
                for item in self.entities
            ],
            "claims": [
                item.to_dict() if hasattr(item, "to_dict") and callable(item.to_dict) else item
                for item in self.claims
            ],
            "sources": [
                item.to_dict() if hasattr(item, "to_dict") and callable(item.to_dict) else item
                for item in self.sources
            ],
            "metadata": self.metadata,
        }


__all__ = ["KnowledgeAsset"]
