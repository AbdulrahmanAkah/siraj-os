from src.application.ports.llm_gateway import LLMGateway
from src.application.llm.core.llm_request import LLMRequest
from src.application.llm.core.llm_response import LLMResponse


class FakeGateway(LLMGateway):

    def generate(
        self,
        request: LLMRequest,
    ) -> LLMResponse:

        return LLMResponse(
            text="FAKE RESPONSE:\n\n" + request.prompt,
            provider="fake",
            model="fake",
        )


__all__ = ["FakeGateway"]


