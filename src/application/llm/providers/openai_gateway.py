import os

from src.application.ports.llm_gateway import LLMGateway
from src.application.llm.core.llm_request import LLMRequest
from src.application.llm.core.llm_response import LLMResponse

import src.application.config.environment_loader


class OpenAIGateway(LLMGateway):

    def __init__(self):

        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set."
            )

        try:
            from openai import OpenAI
        except ModuleNotFoundError as exc:
            raise ValueError(
                "The optional openai package is required only "
                "when the OpenAI gateway is selected."
            ) from exc

        self.client = OpenAI(
            api_key=api_key
        )

    def generate(
        self,
        request: LLMRequest,
    ) -> LLMResponse:

        response = self.client.responses.create(
            model=request.model or "gpt-5",
            input=request.prompt,
        )

        text = response.output_text

        return LLMResponse(
            text=text,
            provider="openai",
            model=request.model or "gpt-5",
            metadata={},
        )


__all__ = ["OpenAIGateway"]
