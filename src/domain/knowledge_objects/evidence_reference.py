from dataclasses import dataclass, field


@dataclass
class EvidenceReference:
    """A precise extracted passage that can support one or more claims."""

    evidence_id: str = ""
    document_id: str = ""
    paragraph_index: int = 0
    sentence_index: int = 0
    text: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


__all__ = ["EvidenceReference"]
