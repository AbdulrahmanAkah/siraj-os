from typing import Dict, List


class NarrativeBuilder:
    def build(self, outline: Dict[str, object]) -> Dict[str, object]:
        title = outline.get("title", "")
        claims = outline.get("claims", [])
        sources = outline.get("sources", [])

        if not isinstance(claims, list):
            claims = [claims]
        if not isinstance(sources, list):
            sources = [sources]

        return {
            "title": title,
            "introduction": [title] if title else [],
            "main_points": [str(item) for item in claims if item is not None],
            "conclusion": ["End of narrative"],
            "sources": [str(item) for item in sources if item is not None],
        }


__all__ = ["NarrativeBuilder"]
