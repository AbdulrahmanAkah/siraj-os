import json
from dataclasses import dataclass, field
from hashlib import sha256


@dataclass
class KnowledgeEdge:
    source: str
    target: str
    relation: str
    metadata: dict[str, object] = field(default_factory=dict)
    relationship_id: str = ""

    def __post_init__(self):
        if not self.relationship_id:
            identity = json.dumps(
                {
                    "source": self.source,
                    "target": self.target,
                    "relation": self.relation,
                    "metadata": self.metadata,
                },
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
            self.relationship_id = f"relationship_{sha256(identity.encode('utf-8')).hexdigest()[:16]}"

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
            "metadata": self.metadata,
            "relationship_id": self.relationship_id,
        }


__all__ = ["KnowledgeEdge"]


