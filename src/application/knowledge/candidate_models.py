
from dataclasses import dataclass, field
from typing import Any

@dataclass
class Candidate:
    kind:str
    value:Any
    source:str=""
    confidence:float=0.0
    metadata:dict=field(default_factory=dict)
    source_reference:object|None=None


