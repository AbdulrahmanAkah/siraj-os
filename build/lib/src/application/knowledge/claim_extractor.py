from src.application.models.knowledge.source_reference import SourceReference

import re

from .base_extractor import BaseExtractor
from .candidate_models import Candidate

DATE = re.compile(r"\b(5\d{2}|6\d{2}|7\d{2}|8\d{2}|9\d{2}|1\d{3}|2\d{3})\b")

VERBS = {
    "is","was","were","are",
    "became","ruled","led","defeated","won","lost",
    "built","created","founded","signed","captured",
    "married","born","died","commanded","discovered"
}

IGNORE_PREFIXES = {
    "wikipedia",
    "according to",
    "historians",
    "many historians",
    "researchers",
    "scholars",
    "it is believed",
    "it is said"
}


class ClaimExtractor(BaseExtractor):

    def extract(self, context):

        text = context.text

        out = []

        for raw in text.splitlines():

            line = raw.strip()

            if not line:
                continue

            lower = line.lower()

            if any(lower.startswith(x) for x in IGNORE_PREFIXES):
                continue

            score = 0.0

            if DATE.search(line):
                score += 0.30

            words = lower.split()

            if any(v in words for v in VERBS):
                score += 0.40

            if len(words) >= 4:
                score += 0.20

            if score < 0.60:
                continue

            out.append(
                Candidate(
                    kind="CLAIM",
                    value=line,
                    source="claim_extractor",
                    confidence=min(score,1.0),
                    source_reference=SourceReference(
                        document_id=context.document_id,
                        document_name=context.document_name,
                        page=context.page,
                        paragraph=context.paragraph,
                        sentence=context.sentence,
                        extractor="claim_extractor",
                    ),
                    metadata={
                        "extractor":"claim_extractor",
                        "has_date":bool(DATE.search(line)),
                        "has_subject":False,
                        "has_verb":any(v in words for v in VERBS),
                    },
                )
            )

        return out


