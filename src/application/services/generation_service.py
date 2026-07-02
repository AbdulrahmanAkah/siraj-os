from application.models.prompt import Prompt
from application.models.script import Script
from application.ports.llm_gateway import LLMGateway


class GenerationService:
    def __init__(self, gateway: LLMGateway) -> None:
        self.gateway = gateway

    def generate(self, prompt: Prompt) -> Script:
        return self.gateway.generate(prompt)


__all__ = ["GenerationService"]
