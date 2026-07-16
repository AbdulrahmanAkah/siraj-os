from src.application.models.knowledge.source_reference import SourceReference

import re

from .base_extractor import BaseExtractor
from .candidate_models import Candidate

PATTERNS = [

    (re.compile(r"(.+?)\s+commanded\s+(.+)", re.I), "commanded"),
    (re.compile(r"(.+?)\s+defeated\s+(.+)", re.I), "defeated"),
    (re.compile(r"(.+?)\s+founded\s+(.+)", re.I), "founded"),
    (re.compile(r"(.+?)\s+built\s+(.+)", re.I), "built"),
    (re.compile(r"(.+?)\s+captured\s+(.+)", re.I), "captured"),
    (re.compile(r"(.+?)\s+signed\s+(.+)", re.I), "signed"),
    (re.compile(r"(.+?)\s+married\s+(.+)", re.I), "married"),
    (re.compile(r"(.+?)\s+ruled\s+(.+)", re.I), "ruled"),

    (re.compile(r"(.+?)\s+is\s+southwest\s+of\s+(.+)", re.I), "southwest_of"),
    (re.compile(r"(.+?)\s+is\s+northeast\s+of\s+(.+)", re.I), "northeast_of"),
    (re.compile(r"(.+?)\s+is\s+north\s+of\s+(.+)", re.I), "north_of"),
    (re.compile(r"(.+?)\s+is\s+south\s+of\s+(.+)", re.I), "south_of"),
    (re.compile(r"(.+?)\s+is\s+east\s+of\s+(.+)", re.I), "east_of"),
    (re.compile(r"(.+?)\s+is\s+west\s+of\s+(.+)", re.I), "west_of"),

]


class RelationshipExtractor(BaseExtractor):

    def extract(self, context):

        text = context.text

        out = []

        for raw in text.splitlines():

            line = raw.strip()

            if not line:
                continue

            for regex, predicate in PATTERNS:

                m = regex.match(line)

                if not m:
                    continue

                subject = m.group(1).strip()

                obj = m.group(2).strip()

                out.append(

                    Candidate(

                        kind="RELATIONSHIP",

                        value={
                            "subject":subject,
                            "predicate":predicate,
                            "object":obj
                        },

                        source="relationship_extractor",

                        confidence=1.0,

                        source_reference=SourceReference(
                            document_id=context.document_id,
                            document_name=context.document_name,
                            page=context.page,
                            paragraph=context.paragraph,
                            sentence=context.sentence,
                            extractor="relationship_extractor",
                        ),

                        metadata={
                            "extractor":"relationship_extractor",
                            "has_subject":True,
                            "has_verb":True
                        }

                    )

                )

        return out


