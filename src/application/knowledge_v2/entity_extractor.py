from src.domain.knowledge_objects.document_context import DocumentContext
from src.domain.knowledge_objects.source_reference import SourceReference

from .base_extractor import BaseExtractor
from .candidate_models import Candidate
from .rule_engine import RuleEngine


class EntityExtractor(BaseExtractor):

    def __init__(self):
        self.rules = RuleEngine()

    def extract(self, context):

        if isinstance(context, str):
            context = DocumentContext(text=context)

        text = context.text

        candidates = []

        for item in self.rules.extract_entities(text):

            candidates.append(
                Candidate(
                    kind="PERSON",
                    value=item["value"],
                    source="entity_extractor",
                    confidence=item.get("confidence", 0.75),
                    metadata={
                        "extractor": "entity_extractor",
                        "rule": "entity"
                    },
                    source_reference=SourceReference(
                        document_id=context.document_id,
                        document_name=context.document_name,
                        page=context.page,
                        paragraph=context.paragraph,
                        sentence=context.sentence,
                        start_offset=0,
                        end_offset=0,
                        extractor="entity_extractor"
                    )
                )
            )

        return candidates

