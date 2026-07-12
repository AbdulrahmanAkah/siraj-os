from application.models.documentary.script import Script


class ScriptGenerator:

    def build(
        self,
        outline,
        narrative,
    ) -> Script:

        parts = []

        parts.append(
            narrative.introduction
        )

        for title, body in zip(
            outline.sections,
            narrative.body,
        ):
            parts.append(
                f"# {title}"
            )
            parts.append(
                body
            )

        parts.append(
            narrative.conclusion
        )

        return Script(
            title=outline.title,
            narration="\n\n".join(parts),
        )


__all__ = [
    "ScriptGenerator",
]
