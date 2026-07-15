from dataclasses import dataclass, field


@dataclass
class Prompt:
    system_prompt: str = ""
    user_prompt: str = ""
    language: str = "ar"
    target_model: str = ""
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "system_prompt": self.system_prompt,
            "user_prompt": self.user_prompt,
            "language": self.language,
            "target_model": self.target_model,
            "metadata": self.metadata,
        }


__all__ = ["Prompt"]


