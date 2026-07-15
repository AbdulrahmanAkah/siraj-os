from .text_normalizer import TextNormalizer


class NameNormalizer:

    def __init__(self):
        self.text = TextNormalizer()

    def normalize(self, name: str) -> str:

        if not name:
            return ""

        name = self.text.normalize(name)

        for prefix in (
            "prophet ",
            "messenger ",
        ):
            if name.startswith(prefix):
                name = name[len(prefix):]

        return name.strip()


