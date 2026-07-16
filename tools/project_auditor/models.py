"""
Shared dataclasses.
"""

from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class ModuleInfo:
    path: Path
    imports: set[str] = field(default_factory=set)
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
