
import re


class Canonicalizer:

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

        text=text.strip().lower()

        text=re.sub(r"[.,;:!?]+","",text)

        text=re.sub(r"\s+"," ",text)

        return text


    @classmethod
    def canonical_entity(cls,text):

        text=cls.normalize(text)

        return cls.aliases.get(text,text)

