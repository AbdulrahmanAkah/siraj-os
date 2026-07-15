from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List
from uuid import UUID, uuid4

from src.domain.knowledge_objects.relationship import Relationship


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
    relationships: List[Relationship] = field(default_factory=list)
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
            "relationships": [
                item.to_dict() if hasattr(item, "to_dict") and callable(item.to_dict) else item
                for item in self.relationships
            ],
            "metadata": self.metadata,
        }

    def add_source(self, source: "Source") -> None:
        self.sources.append(source)

    def add_entity(self, entity: "Entity") -> None:
        self.entities.append(entity)

    def add_claim(self, claim: "Claim") -> None:
        self.claims.append(claim)

    def add_relationship(self, relationship: Relationship) -> None:
        self.relationships.append(relationship)

    def summary(self) -> str:
        entity_names = ", ".join(
            entity.name for entity in self.entities if hasattr(entity, "name") and entity.name
        )
        source_count = len(self.sources)

        return (
            "Knowledge Asset\n"
            f"Title:\n{self.title}\n\n"
            f"Sources:\n{source_count}\n\n"
            f"Entities:\n{entity_names or 'None'}\n\n"
            f"Status:\n{self.status}"
        )

    def validate(self) -> Dict[str, object]:
        errors: List[str] = []

        if not self.title.strip():
            errors.append("Title is required")
        if not self.sources:
            errors.append("At least one source is required")
        if not self.entities:
            errors.append("At least one entity is required")

        return {"valid": not errors, "errors": errors}


__all__ = ["KnowledgeAsset"]


