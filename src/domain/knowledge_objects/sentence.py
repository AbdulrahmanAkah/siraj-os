from dataclasses import dataclass


@dataclass
class Sentence:

    index: int = 0

    text: str = ""

    start_offset: int = 0

    end_offset: int = 0


