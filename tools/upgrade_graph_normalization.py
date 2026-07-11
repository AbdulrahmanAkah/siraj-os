from pathlib import Path

BASE = Path("src/application/knowledge")

files = {
    "text_normalizer.py": '''
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
''',

    "name_normalizer.py": '''
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
''',

    "relationship_normalizer.py": '''
from .text_normalizer import TextNormalizer


class RelationshipNormalizer:

    def __init__(self):
        self.text = TextNormalizer()

    def normalize(self, extraction):

        for r in extraction.relationships:

            r.subject = self.text.normalize(r.subject)
            r.object = self.text.normalize(r.object)
            r.predicate = self.text.normalize(r.predicate)

        return extraction
''',

    "entity_normalizer.py": '''
from .name_normalizer import NameNormalizer
from .text_normalizer import TextNormalizer


class EntityNormalizer:

    def __init__(self):

        self.names = NameNormalizer()
        self.text = TextNormalizer()

    def normalize(self, extraction):

        for p in extraction.persons:
            p.name = self.names.normalize(p.name)

        for e in extraction.events:
            e.name = self.text.normalize(e.name)

        for l in extraction.locations:
            l.name = self.text.normalize(l.name)

        return extraction
''',

    "graph_normalizer.py": '''
from .entity_normalizer import EntityNormalizer
from .relationship_normalizer import RelationshipNormalizer


class GraphNormalizer:

    def __init__(self):

        self.entities = EntityNormalizer()
        self.relationships = RelationshipNormalizer()

    def normalize(self, extraction):

        extraction = self.entities.normalize(extraction)
        extraction = self.relationships.normalize(extraction)

        return extraction
''',

    "normalization_rules.py": '''
NORMALIZATION_RULES = {}
'''
}

BASE.mkdir(parents=True, exist_ok=True)

for name, content in files.items():
    path = BASE / name
    if not path.exists():
        path.write_text(content.strip() + "\\n", encoding="utf-8")
        print("[CREATED]", path)
    else:
        print("[SKIPPED]", path)

pipeline = BASE / "extraction_pipeline.py"

text = pipeline.read_text(encoding="utf-8")

if "graph_normalizer import GraphNormalizer" not in text:
    text = text.replace(
        "from .graph_builder import GraphBuilder",
        "from .graph_builder import GraphBuilder\\nfrom .graph_normalizer import GraphNormalizer",
    )

if "self.graph_normalizer = GraphNormalizer()" not in text:
    text = text.replace(
        "self.graph_builder = GraphBuilder()",
        "self.graph_builder = GraphBuilder()\\n        self.graph_normalizer = GraphNormalizer()",
    )

needle = "extraction=self.relationship_resolver.resolve(extraction)"

if needle in text and "graph_normalizer.normalize" not in text:
    text = text.replace(
        needle,
        needle + "\\n\\n        extraction=self.graph_normalizer.normalize(extraction)",
    )

pipeline.write_text(text, encoding="utf-8")

print()
print("Graph Normalization layer installed successfully.")