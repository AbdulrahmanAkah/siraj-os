import re


class EventCanonicalizer:

    def slug(self, text: str):

        text = text.lower()

        text = text.replace(".", "")
        text = text.replace(",", "")
        text = text.replace("'", "")

        text = re.sub(r"\b(happened|occurred|took place|in|at|on)\b", " ", text)

        text = re.sub(r"\b\d+\s*(ce|ad|bc)?\b", " ", text)

        text = re.sub(r"\s+", " ", text).strip()

        text = text.replace(" ", "_")

        return text

    def run(self, graph):

        for node in graph.nodes:

            if node.type != "EVENT":
                continue

            if "name" not in node.data:
                continue

            original = node.data["name"]

            canonical = self.slug(original)

            node.id = canonical

            node.data["name"] = canonical.replace("_", " ")

        graph.refresh()

        return graph

