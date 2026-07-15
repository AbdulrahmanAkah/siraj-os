from src.application.models.knowledge.source_reference import SourceReference
from src.application.ports.llm_gateway import LLMGateway
from src.application.llm.core.llm_request import LLMRequest

from src.application.knowledge.knowledge_parser import KnowledgeParser
from src.application.knowledge.extraction_result import ExtractionResult


class KnowledgeExtractor:

    def __init__(self, gateway: LLMGateway):
        self.gateway = gateway
        self.parser = KnowledgeParser()

    def extract(
        self,
        text: str,
    ) -> ExtractionResult:

        prompt = f"""
Extract every piece of knowledge from the following text.

Return ONLY valid JSON.

Schema:

{{
  "persons": [],
  "events": [],
  "locations": [],
  "claims": [],
  "statistics": [],
  "timeline": [],
  "relationships": [],
  "sources": []
}}

TEXT:

{text}
"""

        response = self.gateway.generate(
            LLMRequest(
                prompt=prompt
            )
        )

        return self.parser.parse(
            response.text
        )


__all__ = ["KnowledgeExtractor"]


