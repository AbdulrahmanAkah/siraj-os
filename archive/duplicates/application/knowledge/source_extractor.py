from src.application.models.knowledge.source_reference import SourceReference

from .base_extractor import BaseExtractor
from .candidate_models import Candidate


SOURCE_PREFIXES = {
    "source:",
    "sources:",
    "reference:",
    "references:",
    "bibliography:",
    "citation:"
}


class SourceExtractor(BaseExtractor):

    def extract(self, context):

        text = context.text

        out = []

        for raw in text.splitlines():

            line = raw.strip()

            if not line:
                continue

            lower = line.lower()

            if not any(lower.startswith(x) for x in SOURCE_PREFIXES):
                continue

            out.append(

                Candidate(

                    kind="SOURCE",

                    value=line,

                    source="source_extractor",

                    confidence=0.95,

                    source_reference=SourceReference(
                        document_id=context.document_id,
                        document_name=context.document_name,
                        page=context.page,
                        paragraph=context.paragraph,
                        sentence=context.sentence,
                        extractor="source_extractor",
                    ),

                    metadata={
                        "extractor":"source_extractor"
                    }

                )

            )

        return out


