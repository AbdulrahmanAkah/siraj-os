from src.application.knowledge_v2.pipeline import KnowledgeExtractionPipeline
import os

from src.application.llm.providers.openai_gateway import OpenAIGateway
from src.application.llm.providers.gemini_gateway import GeminiGateway
from src.application.llm.providers.manual_gateway import ManualGateway

from src.application.workflow.documentary_workflow import DocumentaryWorkflow


class ProductionPipeline:

    def __init__(self):

        if os.getenv("OPENAI_API_KEY", "").strip():

            gateway = OpenAIGateway()

        elif os.getenv("GEMINI_API_KEY", "").strip():

            gateway = GeminiGateway()

        else:

            gateway = ManualGateway()

        self.workflow = DocumentaryWorkflow(
            gateway
        )

    def run(
        self,
        topic: str,
        sources: list[str],
    ):

        return self.workflow.run(
            topic,
            sources,
        )


__all__ = ["ProductionPipeline"]


