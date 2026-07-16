from src.application.llm.core.fake_gateway import FakeGateway
from src.application.llm.core.llm_request import LLMRequest

gateway = FakeGateway()

response = gateway.generate(
    LLMRequest(
        prompt="Hello Siraj"
    )
)

print(response)

assert response.provider == "fake"
assert response.model == "fake"
assert "Hello Siraj" in response.text

print("LLMGateway OK")


