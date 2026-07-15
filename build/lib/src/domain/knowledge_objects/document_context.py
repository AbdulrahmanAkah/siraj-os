from dataclasses import dataclass

@dataclass(slots=True)
class DocumentContext:
    text: str
    document_id: str = ""
    document_name: str = ""
    source_type: str = ""
    page: int = 0
    paragraph: int = 0
    sentence: int = 0


