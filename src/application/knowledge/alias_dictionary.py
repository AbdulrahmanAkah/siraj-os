from .canonicalizer import Canonicalizer


class AliasDictionary:

    def __init__(self):

        self.aliases = {

            "Muhammad": [
                "muhammad",
                "Muhammad",
                "the prophet",
                "messenger of allah",
                "prophet"
            ],

            "Madinah": [
                "madinah",
                "medina",
                "al madinah",
                "madina"
            ],

            "Badr": [
                "badr",
                "battle of badr"
            ]
        }

        self.reverse = {}

        for display_name, aliases in self.aliases.items():

            for alias in aliases:

                self.reverse[
                    Canonicalizer.canonical_name(alias)
                ] = display_name

    def resolve(self, text):

        key = Canonicalizer.canonical_name(text)

        return self.reverse.get(key, text)


