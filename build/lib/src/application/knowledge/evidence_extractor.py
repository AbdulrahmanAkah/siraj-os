from src.application.models.knowledge.source_reference import SourceReference

from .base_extractor import BaseExtractor
from .candidate_models import Candidate

EVIDENCE_PREFIXES = {
    "according to",
    "reported by",
    "documented by",
    "stated by",
    "recorded by",
    "cited by",
    "source:",
    "reference:"
}


class EvidenceExtractor(BaseExtractor):

    def extract(self, context):

        text = context.text

        out = []

        for raw in text.splitlines():

            line = raw.strip()

            if not line:
                continue

            lower = line.lower()

            if not any(lower.startswith(x) for x in EVIDENCE_PREFIXES):
                continue

            out.append(

                Candidate(

                    kind="EVIDENCE",

                    value=line,

                    source="evidence_extractor",

                    confidence=0.95,

                    source_reference=SourceReference(
                        document_id=context.document_id,
                        document_name=context.document_name,
                        page=context.page,
                        paragraph=context.paragraph,
                        sentence=context.sentence,
                        extractor="evidence_extractor",
                    ),

                    metadata={
                        "extractor":"evidence_extractor"
                    }

                )

            )

        return out


