
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

@dataclass(slots=True)
class KnowledgeChunk:
    metadata: dict[str, Any] = field(default_factory=dict)


