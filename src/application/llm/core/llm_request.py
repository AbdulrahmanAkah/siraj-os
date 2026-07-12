from dataclasses import dataclass, field


@dataclass
class LLMRequest:
    prompt: str
    system_prompt: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    metadata: dict[str, object] = field(default_factory=dict)


__all__ = ["LLMRequest"]


