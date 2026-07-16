
from dataclasses import dataclass, field
from typing import List

@dataclass(slots=True)
class Document:
    title:str
    text:str
    language:str="unknown"
    paragraphs:List[str]=field(default_factory=list)


