from pathlib import Path

path = Path("src/application/knowledge/knowledge_graph_builder.py")
text = path.read_text(encoding="utf-8")

old = """        for r in extraction.relationships:

            graph.add_relationship(r)

            graph.add_edge(
                KnowledgeEdge(
                    source=Canonicalizer.normalize_text(r.subject),
                    target=Canonicalizer.normalize_text(r.object),
                    relation=Canonicalizer.normalize_text(r.predicate),
                )
            )
"""

new = """        for r in extraction.relationships:

            graph.add_relationship(r)

            source = Canonicalizer.normalize_text(r.subject)
            target = Canonicalizer.normalize_text(r.object)

            if graph.get_node(source) is None:
                graph.add_node(
                    KnowledgeNode(
                        id=source,
                        type="ENTITY",
                        data={"name": r.subject},
                    )
                )

            if graph.get_node(target) is None:
                graph.add_node(
                    KnowledgeNode(
                        id=target,
                        type="ENTITY",
                        data={"name": r.object},
                    )
                )

            graph.add_edge(
                KnowledgeEdge(
                    source=source,
                    target=target,
                    relation=Canonicalizer.normalize_text(r.predicate),
                )
            )
"""

if old not in text:
    raise SystemExit("Target block not found. Builder may already be modified.")

path.write_text(text.replace(old, new), encoding="utf-8")
print("KnowledgeGraphBuilder upgraded successfully.")
