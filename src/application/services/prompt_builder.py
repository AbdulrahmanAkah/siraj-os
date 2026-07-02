from application.models.content_specification import ContentSpecification
from application.models.narrative_plan import NarrativePlan
from application.models.prompt import Prompt


class PromptBuilder:
    def build(
        self,
        plan: NarrativePlan,
        specification: ContentSpecification,
    ) -> Prompt:
        user_prompt = (
            f"Title:\n{plan.title}\n\n"
            f"Hook:\n{chr(10).join(plan.hook)}\n\n"
            f"Background:\n{chr(10).join(plan.background)}\n\n"
            f"Main Story:\n{chr(10).join(plan.main_story)}\n\n"
            f"Conclusion:\n{chr(10).join(plan.conclusion)}\n\n"
            f"Sources:\n{chr(10).join(plan.sources)}\n\n"
            f"Target Platform:\n{specification.platform}\n\n"
            f"Style:\n{specification.style}\n\n"
            f"Audience:\n{specification.target_audience}\n\n"
            f"Tone:\n{specification.tone}\n\n"
            f"Duration:\n{specification.duration_minutes} minutes\n\n"
            f"Include Citations:\n{specification.include_citations}"
        )

        return Prompt(
            system_prompt="You are an expert educational documentary writer.",
            user_prompt=user_prompt,
            language=specification.language,
            target_model="",
            metadata={
                "title": plan.title,
                "platform": specification.platform,
                "style": specification.style,
                "audience": specification.target_audience,
            },
        )


__all__ = ["PromptBuilder"]
