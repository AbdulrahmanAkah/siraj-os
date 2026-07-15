from dataclasses import dataclass, field

from src.domain.knowledge_objects.sentence import Sentence


@dataclass
class Paragraph:

    index: int = 0

    text: str = ""

    sentences: list[Sentence] = field(default_factory=list)


