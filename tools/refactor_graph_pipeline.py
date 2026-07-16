from pathlib import Path
import textwrap

ROOT = Path("src")

# -------------------------------------------------
# 1) Canonicalizer
# -------------------------------------------------

canonicalizer = textwrap.dedent("""
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

        text=re.sub(r"\\s+"," ",text)

        return text


    @classmethod
    def canonical_entity(cls,text):

        text=cls.normalize(text)

        return cls.aliases.get(text,text)
""")

(ROOT/"application/knowledge/canonicalizer.py").write_text(
    canonicalizer,
    encoding="utf8"
)

# -------------------------------------------------
# 2) Graph Builder
# -------------------------------------------------

builder = ROOT/"application/knowledge/knowledge_graph_builder.py"

txt=builder.read_text(encoding="utf8")

txt=txt.replace(
"Canonicalizer.normalize_text(r.subject)",
"Canonicalizer.canonical_entity(r.subject)"
)

txt=txt.replace(
"Canonicalizer.normalize_text(r.object)",
"Canonicalizer.canonical_entity(r.object)"
)

builder.write_text(txt,encoding="utf8")

# -------------------------------------------------
# 3) Graph Resolver
# -------------------------------------------------

resolver=ROOT/"domain/knowledge_graph/graph_resolver.py"

txt=resolver.read_text(encoding="utf8")

txt=txt.replace(
"edge.source.casefold()",
"Canonicalizer.canonical_entity(edge.source)"
)

txt=txt.replace(
"edge.target.casefold()",
"Canonicalizer.canonical_entity(edge.target)"
)

txt=txt.replace(
"node.id.casefold()",
"Canonicalizer.canonical_entity(node.id)"
)

txt=txt.replace(
'lookup[node.data["name"].casefold()]',
'lookup[Canonicalizer.canonical_entity(node.data["name"])]'
)

if "Canonicalizer" not in txt:
    txt="from src.application.knowledge.canonicalizer import Canonicalizer\n"+txt

resolver.write_text(txt,encoding="utf8")

print("="*60)
print("GRAPH PIPELINE REFACTORED")
print("="*60)