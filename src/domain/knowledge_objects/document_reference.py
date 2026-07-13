from dataclasses import dataclass, field


@dataclass
class DocumentReference:
    """A stable document identity within an extraction result."""

    document_id: str = ""
    title: str = ""
    source_id: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


__all__ = ["DocumentReference"]
