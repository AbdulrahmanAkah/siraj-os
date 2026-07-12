import re

from src.application.models.knowledge.source_reference import SourceReference

from .base_extractor import BaseExtractor
from .candidate_models import Candidate


YEAR = re.compile(r"\b(5\d{2}|6\d{2}|7\d{2}|8\d{2}|9\d{2}|1\d{3}|2\d{3})\b")


EVENT_PATTERNS = [

    r"^(battle of\s+.+?)(?=\s+(?:happened|occurred|took|began|started|ended|was|is|in)\b|\.|,|$)",

    r"^(war of\s+.+?)(?=\s+(?:happened|occurred|took|began|started|ended|was|is|in)\b|\.|,|$)",

    r"^(siege of\s+.+?)(?=\s+(?:happened|occurred|took|began|started|ended|was|is|in)\b|\.|,|$)",

    r"^(expedition of\s+.+?)(?=\s+(?:happened|occurred|took|began|started|ended|was|is|in)\b|\.|,|$)",

    r"^(campaign of\s+.+?)(?=\s+(?:happened|occurred|took|began|started|ended|was|is|in)\b|\.|,|$)",

    r"^(migration of\s+.+?)(?=\s+(?:happened|occurred|took|began|started|ended|was|is|in)\b|\.|,|$)",

    r"^(treaty of\s+.+?)(?=\s+(?:happened|occurred|took|began|started|ended|was|is|in)\b|\.|,|$)",
]


IGNORE_PREFIXES = {
    "wikipedia",
    "according to",
    "historians",
    "many historians",
    "researchers",
    "scholars",
    "it is believed",
    "it is said",
}


class EventExtractor(BaseExtractor):

    def extract_event_name(self, line: str):

        clean = line.strip()

        for pattern in EVENT_PATTERNS:

            m = re.search(pattern, clean, flags=re.IGNORECASE)

            if m:
                return m.group(1).strip()

        return clean

    def extract(self, context):

        out = []

        for raw in context.text.splitlines():

            line = raw.strip()

            if not line:
                continue

            lower = line.lower()

            if any(lower.startswith(x) for x in IGNORE_PREFIXES):
                continue

            event_name = self.extract_event_name(line)

            if event_name == line:
                continue

            score = 0.95 if YEAR.search(line) else 0.85

            out.append(
                Candidate(
                    kind="EVENT",
                    value=event_name,
                    source="event_extractor",
                    confidence=score,
                    source_reference=SourceReference(
                        document_id=context.document_id,
                        document_name=context.document_name,
                        page=context.page,
                        paragraph=context.paragraph,
                        sentence=context.sentence,
                        extractor="event_extractor",
                    ),
                    metadata={
                        "extractor": "event_extractor",
                        "original_text": line,
                        "has_date": bool(YEAR.search(line)),
                        "has_subject": False,
                        "has_verb": False,
                    },
                )
            )

        return out
