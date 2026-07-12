class TextNormalizer:

    def normalize(self, text: str) -> str:

        if not text:
            return ""

        text = text.strip()
        text = text.replace(".", "")
        text = text.replace(",", "")
        text = text.replace(";", "")
        text = text.replace(":", "")
        text = text.replace("  ", " ")
        text = text.lower()

        if text.startswith("the "):
            text = text[4:]

        return text


