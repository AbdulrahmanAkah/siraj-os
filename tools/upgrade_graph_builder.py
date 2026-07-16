from pathlib import Path

path = Path("src/application/knowledge/knowledge_graph_builder.py")

code = '''from src.domain.knowledge_graph.knowledge_graph import KnowledgeGraph
from src.domain.knowledge_graph.knowledge_node import KnowledgeNode
from src.domain.knowledge_graph.knowledge_edge import KnowledgeEdge
from src.application.knowledge.canonicalizer import Canonicalizer


class KnowledgeGraphBuilder:

    def build(self, extraction):

        graph = KnowledgeGraph()

        def add(obj, node_type, node_id):

            graph.add_node(
                KnowledgeNode(
                    id=node_id,
                    type=node_type,
                    data=obj.to_dict(),
                )
            )

        for x in extraction.persons:
            add(
                x,
                "PERSON",
                Canonicalizer.canonical_name(x.name),
            )

        for x in extraction.events:
            add(
                x,
                "EVENT",
                Canonicalizer.normalize_text(x.name),
            )

        for x in extraction.locations:
            add(
                x,
                "LOCATION",
                Canonicalizer.canonical_name(x.name),
            )

        for i, x in enumerate(extraction.claims):
            add(x, "CLAIM", f"claim_{i}")

        for i, x in enumerate(extraction.statistics):
            add(x, "STATISTIC", f"statistic_{i}")

        for i, x in enumerate(extraction.timeline):
            add(x, "TIMELINE_EVENT", f"timeline_{i}")

        for i, x in enumerate(extraction.sources):
            add(x, "SOURCE", f"source_{i}")

        for r in extraction.relationships:

            graph.add_relationship(r)

            graph.add_edge(
                KnowledgeEdge(
                    source=Canonicalizer.normalize_text(r.subject),
                    target=Canonicalizer.normalize_text(r.object),
                    relation=Canonicalizer.normalize_text(r.predicate),
                )
            )

        graph.refresh()

        return graph


__all__ = ["KnowledgeGraphBuilder"]
'''

path.write_text(code, encoding="utf-8")

print("KnowledgeGraphBuilder upgraded successfully.")
