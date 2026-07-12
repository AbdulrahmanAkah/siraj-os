from src.application.models.knowledge.source_reference import SourceReference

from .base_extractor import BaseExtractor
from .candidate_models import Candidate
from .rule_engine import RuleEngine


class LocationExtractor(BaseExtractor):

    def __init__(self):
        self.rules = RuleEngine()

    def extract(self, context):

        text = context.text

        out = []

        for item in self.rules.extract_locations(text):

            out.append(

                Candidate(

                    kind="LOCATION",

                    value=item["value"],

                    source="location_extractor",

                    confidence=item.get("confidence",0.95),

                    source_reference=SourceReference(
                        document_id=context.document_id,
                        document_name=context.document_name,
                        page=context.page,
                        paragraph=context.paragraph,
                        sentence=context.sentence,
                        extractor="location_extractor",
                    ),

                    metadata={
                        "extractor":"location_extractor",
                        "rule":"location"
                    }

                )

            )

        return out



