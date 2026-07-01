from dataclasses import dataclass, field
from typing import Dict, Optional
from uuid import uuid4


@dataclass
class Source:
    source_id: str = field(default_factory=lambda: str(uuid4()))
    title: str = ""
    source_type: str = ""
    author: str = ""
    publisher: str = ""
    publication_year: Optional[int] = None
    language: str = "ar"
    url: str = ""
    notes: str = ""
    metadata: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "source_type": self.source_type,
            "author": self.author,
            "publisher": self.publisher,
            "publication_year": self.publication_year,
            "language": self.language,
            "url": self.url,
            "notes": self.notes,
            "metadata": self.metadata,
        }


__all__ = ["Source"]
