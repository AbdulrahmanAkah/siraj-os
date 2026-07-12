from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    metadata: dict[str, object] = field(default_factory=dict)


__all__ = ["LLMResponse"]


