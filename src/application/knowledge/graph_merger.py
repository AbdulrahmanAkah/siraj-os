class GraphMerger:

    def merge(self, graph):

        # Merge duplicate nodes
        mapping = {}
        unique_nodes = []

        for node in graph.nodes:

            canonical = node.id.strip().lower()

            if canonical not in mapping:
                mapping[canonical] = node.id
                unique_nodes.append(node)

        # Redirect edges
        for edge in graph.edges:

            edge.source = mapping.get(edge.source.strip().lower(), edge.source)

            edge.target = mapping.get(edge.target.strip().lower(), edge.target)

        # Redirect relationships
        for rel in graph.relationships:

            rel.subject = mapping.get(rel.subject.strip().lower(), rel.subject)

            rel.object = mapping.get(rel.object.strip().lower(), rel.object)

        graph.nodes = unique_nodes

        # Remove duplicate edges
        seen = {}
        new_edges = []

        for edge in graph.edges:

            key = (edge.source, edge.relation, edge.target)

            if key not in seen:
                seen[key] = True
                new_edges.append(edge)

        graph.edges = new_edges

        # Remove duplicate relationships
        seen = {}
        new_relationships = []

        for rel in graph.relationships:

            key = (rel.subject, rel.predicate, rel.object)

            if key not in seen:
                seen[key] = True
                new_relationships.append(rel)

        graph.relationships = new_relationships

        graph.refresh()

        return graph

