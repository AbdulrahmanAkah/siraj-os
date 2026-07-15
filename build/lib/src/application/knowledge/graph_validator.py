class GraphIntegrityValidator:


    def validate(self, graph):

        node_ids = {
            node.id
            for node in graph.nodes
        }


        errors = []


        for edge in graph.edges:

            if edge.source not in node_ids:
                errors.append(
                    f"Missing source node: {edge.source}"
                )


            if edge.target not in node_ids:
                errors.append(
                    f"Missing target node: {edge.target}"
                )


        for rel in graph.relationships:

            if rel.subject not in node_ids:
                errors.append(
                    f"Missing relationship subject: {rel.subject}"
                )


            if rel.object not in node_ids:
                errors.append(
                    f"Missing relationship object: {rel.object}"
                )


        if errors:

            print("="*70)
            print("GRAPH INTEGRITY ERRORS")
            print("="*70)

            for e in errors:
                print(e)

            print("="*70)


        else:

            print("="*70)
            print("GRAPH INTEGRITY CHECK PASSED")
            print("="*70)


        return graph

