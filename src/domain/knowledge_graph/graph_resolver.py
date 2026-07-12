
from src.domain.knowledge_graph.knowledge_node import KnowledgeNode


class GraphResolver:

    def resolve(self, graph):

        print("###DEBUG_RESOLVER###")
        print("nodes before:", len(graph.nodes))
        print("edges before:", len(graph.edges))


        lookup = {}

        for node in graph.nodes:

            lookup[Canonicalizer.canonical_entity(node.id)] = node.id

            if "name" in node.data:
                lookup[Canonicalizer.canonical_entity(node.data["name"])] = node.id

        for edge in graph.edges:
            print("EDGE BEFORE:", edge.source, "->", edge.target)


            s = lookup.get(Canonicalizer.canonical_entity(edge.source))

            if s is None:

                node = KnowledgeNode(
                    id=edge.source,
                    type="UNKNOWN",
                    data={"name": edge.source},
                    metadata={"placeholder": True},
                )

                graph.add_node(node)

                lookup[Canonicalizer.canonical_entity(edge.source)] = edge.source

                s = edge.source

            t = lookup.get(Canonicalizer.canonical_entity(edge.target))

            if t is None:

                node = KnowledgeNode(
                    id=edge.target,
                    type="UNKNOWN",
                    data={"name": edge.target},
                    metadata={"placeholder": True},
                )

                graph.add_node(node)

                lookup[Canonicalizer.canonical_entity(edge.target)] = edge.target

                t = edge.target

            edge.source = s
            edge.target = t

        print("AFTER RESOLVE:")
        for e in graph.edges:
            print(e.source, "->", e.target)

        graph.refresh()


        return graph


__all__ = ["GraphResolver"]


