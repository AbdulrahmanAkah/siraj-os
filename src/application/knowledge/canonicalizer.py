
import re


class Canonicalizer:

    _INVISIBLE_FORMATTING_CHARACTERS = "\ufeff\u200b\u200c\u200d"

    aliases = {

        "the prophet":"muhammad",
        "prophet muhammad":"muhammad",
        "muhammad":"muhammad",

        "medina":"madinah",

        "the muslims":"muslims",

        "muslim army":"muslim army",
    }

    @classmethod
    def normalize(cls,text):

        if text is None:
            return ""

        text=text.replace("\ufeff", "").replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")

        text=text.strip().lower()

        text=re.sub(r"[.,;:!?]+","",text)

        text=re.sub(r"\s+"," ",text)

        return text


    @classmethod
    def sanitize_text(cls, text):

        if text is None:
            return ""

        return str(text).translate(
            str.maketrans("", "", cls._INVISIBLE_FORMATTING_CHARACTERS)
        )


    @classmethod
    def canonical_entity(cls,text):

        text=cls.normalize(text)

        return cls.aliases.get(text,text)


    @classmethod
    def canonical_name(cls,name):
        return cls.canonical_entity(name)


    @classmethod
    def normalize_text(cls,value):
        return cls.canonical_entity(value)

