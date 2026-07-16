from dataclasses import dataclass
from hashlib import sha256

from src.domain.knowledge_objects.knowledge_object import KnowledgeObject


@dataclass
class Source(KnowledgeObject):
    title: str = ""
    type: str = ""
    url: str = ""
    source_id: str = ""

    def __post_init__(self):
        if not self.source_id:
            identity = f"{self.title}\x00{self.url}\x00{self.type}"
            self.source_id = f"source_{sha256(identity.encode('utf-8')).hexdigest()[:16]}"


__all__ = ["Source"]
