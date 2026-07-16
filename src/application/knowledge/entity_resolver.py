import re

from .canonical_aliases import CANONICAL_ALIASES


class EntityResolver:

    def __init__(self):
        self.alias_map = {}

    def build_alias_map(self):

        self.alias_map = {}

        for canonical, aliases in CANONICAL_ALIASES.items():

            for alias in aliases:

                key = re.sub(r"\s+", " ", alias.lower()).strip()

                self.alias_map[key] = canonical

    def normalize_name(self, text: str):

        key = re.sub(r"\s+", " ", text.lower()).strip()

        return self.alias_map.get(key, text)

    def resolve(self, extraction):

        self.build_alias_map()

        for person in extraction.persons:
            person.name = self.normalize_name(person.name)

        for rel in extraction.relationships:
            rel.subject = self.normalize_name(rel.subject)
            rel.object = self.normalize_name(rel.object)

        for claim in extraction.claims:

            text = claim.text

            for alias, canonical in sorted(
                self.alias_map.items(),
                key=lambda x: len(x[0]),
                reverse=True,
            ):
                text = re.sub(
                    r"\b" + re.escape(alias) + r"\b",
                    canonical,
                    text,
                    flags=re.IGNORECASE,
                )

            claim.text = text

        for event in extraction.events:

            text = event.name

            for alias, canonical in sorted(
                self.alias_map.items(),
                key=lambda x: len(x[0]),
                reverse=True,
            ):
                text = re.sub(
                    r"\b" + re.escape(alias) + r"\b",
                    canonical,
                    text,
                    flags=re.IGNORECASE,
                )

            event.name = text

        return extraction

    def same(self, a: str, b: str) -> bool:
        self.build_alias_map()
        return self.normalize_name(a) == self.normalize_name(b)



