from src.application.models.organized_knowledge import OrganizedKnowledge
from src.application.models.narrative_plan import NarrativePlan


class NarrativePlanner:
    def build(self, knowledge: OrganizedKnowledge) -> NarrativePlan:
        hook = list(knowledge.claims[:1]) if knowledge.claims else []
        background = [knowledge.description] if knowledge.description else []
        main_story = list(knowledge.claims)
        conclusion = ["Summary and key lessons."]

        return NarrativePlan(
            title=knowledge.primary_topic,
            hook=hook,
            background=background,
            main_story=main_story,
            conclusion=conclusion,
            sources=list(knowledge.sources),
            metadata={},
        )


__all__ = ["NarrativePlanner"]


