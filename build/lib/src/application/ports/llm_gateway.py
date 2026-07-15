from abc import ABC, abstractmethod

from src.application.models.prompt import Prompt
from src.application.models.script import Script


class LLMGateway(ABC):
    @abstractmethod
    def generate(
        self,
        prompt: Prompt,
    ) -> Script:
        ...


__all__ = ["LLMGateway"]


