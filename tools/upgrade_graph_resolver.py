from pathlib import Path
import textwrap

root = Path("src/domain/knowledge_graph")
root.mkdir(parents=True, exist_ok=True)

resolver = textwrap.dedent("""
from src.domain.knowledge_graph.knowledge_node import KnowledgeNode


class GraphResolver:

    def resolve(self, graph):

        lookup = {}

        for node in graph.nodes:

            lookup[node.id.casefold()] = node.id

            if "name" in node.data:
                lookup[node.data["name"].casefold()] = node.id

        for edge in graph.edges:

            s = lookup.get(edge.source.casefold())

            if s is None:

                node = KnowledgeNode(
                    id=edge.source,
                    type="UNKNOWN",
                    data={"name": edge.source},
                    metadata={"placeholder": True},
                )

                graph.add_node(node)

                lookup[edge.source.casefold()] = edge.source

                s = edge.source

            t = lookup.get(edge.target.casefold())

            if t is None:

                node = KnowledgeNode(
                    id=edge.target,
                    type="UNKNOWN",
                    data={"name": edge.target},
                    metadata={"placeholder": True},
                )

                graph.add_node(node)

                lookup[edge.target.casefold()] = edge.target

                t = edge.target

            edge.source = s
            edge.target = t

        graph.refresh()

        return graph


__all__ = ["GraphResolver"]
""")

(root / "graph_resolver.py").write_text(resolver, encoding="utf-8")

builder_path = Path("src/application/knowledge/knowledge_graph_builder.py")

txt = builder_path.read_text(encoding="utf-8")

if "GraphResolver" not in txt:
    txt = txt.replace(
        "from src.domain.knowledge_graph.knowledge_edge import KnowledgeEdge",
        "from src.domain.knowledge_graph.knowledge_edge import KnowledgeEdge\\nfrom src.domain.knowledge_graph.graph_resolver import GraphResolver"
    )

if "resolver = GraphResolver()" not in txt:
    txt = txt.replace(
        "graph.refresh()",
        "resolver = GraphResolver()\\n        resolver.resolve(graph)"
    )

builder_path.write_text(txt, encoding="utf-8")

print("=" * 60)
print("GraphResolver created.")
print("KnowledgeGraphBuilder upgraded.")
print("=" * 60)
