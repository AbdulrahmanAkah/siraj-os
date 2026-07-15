from src.application.models.prompt import Prompt
from src.application.models.script import Script
from src.application.ports.llm_gateway import LLMGateway


class MockLLMProvider(LLMGateway):
    def generate(self, prompt: Prompt) -> Script:
        title = ""
        metadata = prompt.metadata or {}
        if isinstance(metadata, dict) and "title" in metadata:
            title = str(metadata["title"])

        if not title:
            title = "Generated Script"

        return Script(
            title=title,
            introduction="This is a placeholder introduction.",
            body=prompt.user_prompt,
            conclusion="End of document",
            citations=[],
            language=prompt.language,
            metadata={"provider": "mock"},
        )


__all__ = ["MockLLMProvider"]


