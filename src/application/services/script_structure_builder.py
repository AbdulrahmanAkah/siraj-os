from src.application.models.outline import Outline
from src.application.models.script_structure import ScriptStructure


class ScriptStructureBuilder:
    def build(self, outline: Outline) -> ScriptStructure:
        title = outline.title
        claims = outline.claims
        sources = outline.sources

        return ScriptStructure(
            title=title,
            introduction=[title] if title else [],
            main_points=[str(item) for item in claims if item is not None],
            conclusion=["End of document"],
            sources=[str(item) for item in sources if item is not None],
        )


__all__ = ["ScriptStructureBuilder"]


