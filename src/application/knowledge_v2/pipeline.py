from .entity_extractor import EntityExtractor
from .event_extractor import EventExtractor
from .relation_extractor import RelationExtractor
from .source_extractor import SourceExtractor
from .timeline_extractor import TimelineExtractor
from .fact_extractor import FactExtractor


class KnowledgeExtractionPipeline:

    def __init__(self):

        self.steps = [
            EntityExtractor(),
            EventExtractor(),
            RelationExtractor(),
            SourceExtractor(),
            TimelineExtractor(),
            FactExtractor(),
        ]


    def extract(self, text):

        context = {}

        for step in self.steps:
            context.update(
                step.extract(
                    text,
                    context
                )
            )

        return context


__all__ = [
    "KnowledgeExtractionPipeline"
]
