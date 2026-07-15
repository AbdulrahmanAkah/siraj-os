from src.application.knowledge.utils.model_factory import create_model

import json

from src.application.knowledge.extraction_result import ExtractionResult


from src.domain.knowledge_objects.relationship import Relationship


class KnowledgeParser:

    def parse(self, raw: str) -> ExtractionResult:

        data = json.loads(raw)

        result = ExtractionResult()

        result.persons = [
            create_model("person",x)
            for x in data.get("persons", [])
        ]

        result.events = [
            create_model("event",x)
            for x in data.get("events", [])
        ]

        result.locations = [
            create_model("location",x)
            for x in data.get("locations", [])
        ]

        result.claims = [
            create_model("claim",x)
            for x in data.get("claims", [])
        ]

        result.statistics = [
            create_model("statistic",x)
            for x in data.get("statistics", [])
        ]

        result.timeline = [
            create_model("timeline", x)
            for x in data.get("timeline", [])
        ]

        result.relationships = [
            Relationship(
    subject=x.get("subject", x.get("source", "")),
    predicate=x.get("predicate", x.get("relation", "")),
    object=x.get("object", x.get("target", "")),
)
            for x in data.get("relationships", [])
        ]

        result.sources = [
            create_model("source",x)
            for x in data.get("sources", [])
        ]

        return result


__all__ = ["KnowledgeParser"]





