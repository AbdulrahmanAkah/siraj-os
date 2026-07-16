import re

class EntityResolver:

    TITLES = {
        "prophet",
        "king",
        "queen",
        "president",
        "dr",
        "doctor",
        "mr",
        "mrs",
        "ms",
        "general"
    }

    @staticmethod
    def normalize(value: str) -> str:
        if value is None:
            return ""

        value = value.lower().strip()
        value = re.sub(r"[.,;:!?]", "", value)

        words = value.split()

        words = [
            w for w in words
            if w not in EntityResolver.TITLES
        ]

        words = [
            w for w in words
            if w not in {"the", "a", "an"}
        ]

        return " ".join(words)

    @staticmethod
    def same(a: str, b: str) -> bool:
        return EntityResolver.normalize(a) == EntityResolver.normalize(b)


