from abc import ABC, abstractmethod

from application.models.prompt import Prompt
from application.models.script import Script


class LLMGateway(ABC):
    @abstractmethod
    def generate(
        self,
        prompt: Prompt,
    ) -> Script:
        ...


__all__ = ["LLMGateway"]
