from src.domain.knowledge_objects.document_context import DocumentContext
from src.domain.knowledge_objects.source_reference import SourceReference

from .base_extractor import BaseExtractor
from .candidate_models import Candidate
from .rule_engine import RuleEngine


class EntityExtractor(BaseExtractor):

    def __init__(self):
        self.rules = RuleEngine()

    def extract(self, text, context):

        document_context = DocumentContext(text=text)

        candidates = []

        for item in self.rules.extract_entities(text):

            candidates.append(
                Candidate(
                    kind=item.get("kind", "PERSON"),
                    value=item["value"],
                    source="entity_extractor",
                    confidence=item.get("confidence", 0.75),
                    metadata={
                        "extractor": "entity_extractor",
                        "rule": "entity"
                    },
                    source_reference=SourceReference(
                        document_id=document_context.document_id,
                        document_name=document_context.document_name,
                        page=document_context.page,
                        paragraph=document_context.paragraph,
                        sentence=document_context.sentence,
                        start_offset=0,
                        end_offset=0,
                        extractor="entity_extractor"
                    )
                )
            )

        return {"entities": candidates}

