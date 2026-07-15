import os
from dataclasses import dataclass

from src.application.config.environment_loader import *


@dataclass
class Settings:

    provider: str = os.getenv("LLM_PROVIDER", "fake")

    model: str = os.getenv("LLM_MODEL", "fake")

    temperature: float = float(
        os.getenv("LLM_TEMPERATURE", "0.7")
    )

    max_tokens: int = int(
        os.getenv("LLM_MAX_TOKENS", "4096")
    )

    openai_api_key: str = os.getenv(
        "OPENAI_API_KEY",
        "",
    )

    gemini_api_key: str = os.getenv(
        "GEMINI_API_KEY",
        "",
    )


settings = Settings()

__all__ = [
    "Settings",
    "settings",
]


