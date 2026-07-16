from src.application.models.documentary.script import Script


class ScriptGenerator:

    def build(
        self,
        outline,
        narrative,
    ) -> Script:

        parts = [narrative.introduction]

        for title, body in zip(
            outline.sections,
            narrative.body,
        ):
            parts.append(f"{title}.\n{body}")

        parts.append(
            narrative.conclusion
        )

        narration = "\n\n".join(parts)

        return Script(
            title=outline.title,
            introduction=narrative.introduction,
            body="\n\n".join(narrative.body),
            conclusion=narrative.conclusion,
            narration=narration,
        )


__all__ = [
    "ScriptGenerator",
]
