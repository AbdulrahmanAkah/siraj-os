from collections import defaultdict

class EntityCanonicalizer:

    def canonical(self, text: str) -> str:
        return (
            text.strip()
                .lower()
                .replace(".", "")
                .replace(",", "")
                .replace("  ", " ")
        )

    def run(self, graph):

        node_map = {}
        canonical_nodes = []

        for node in graph.nodes:

            node.id = self.canonical(node.id)

            if "name" in node.data:
                node.data["name"] = self.canonical(node.data["name"])

            key = (node.type, node.id)

            if key not in node_map:
                node_map[key] = node
                canonical_nodes.append(node)

        graph.nodes = canonical_nodes

        valid_ids = {n.id for n in graph.nodes}

        created = {}

        for edge in graph.edges:

            edge.source = self.canonical(edge.source)
            edge.target = self.canonical(edge.target)

            if edge.source not in valid_ids:

                if edge.source not in created:
                    from src.domain.knowledge_graph.knowledge_node import KnowledgeNode
                    created[edge.source] = KnowledgeNode(
                        id=edge.source,
                        type="ENTITY",
                        data={"name": edge.source},
                    )

            if edge.target not in valid_ids:

                if edge.target not in created:
                    from src.domain.knowledge_graph.knowledge_node import KnowledgeNode
                    created[edge.target] = KnowledgeNode(
                        id=edge.target,
                        type="ENTITY",
                        data={"name": edge.target},
                    )

        graph.nodes.extend(created.values())

        unique = {}

        for edge in graph.edges:
            unique[(edge.source, edge.relation, edge.target)] = edge

        graph.edges = list(unique.values())

        for rel in graph.relationships:

            rel.subject = self.canonical(rel.subject)
            rel.object = self.canonical(rel.object)

        graph.refresh()

        return graph

