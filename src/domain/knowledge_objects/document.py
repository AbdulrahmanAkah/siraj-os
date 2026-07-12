from dataclasses import dataclass, field


@dataclass
class Document:

    document_id: str = ""

    document_name: str = ""

    source: str = ""

    text: str = ""

    language: str = ""

    metadata: dict = field(default_factory=dict)


