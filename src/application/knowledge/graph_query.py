class GraphQuery:

    def __init__(self, graph):
        self.graph = graph


    def node(self, node_id):
        return self.graph.get_node(node_id)


    def nodes_of_type(self, node_type):
        return self.graph.get_nodes_by_type(node_type)


    def outgoing(self, node_id):
        return self.graph.outgoing(node_id)


    def incoming(self, node_id):
        return self.graph.incoming(node_id)


    def neighbors(self, node_id):
        result = []

        for edge in self.graph.outgoing(node_id):
            node = self.graph.get_node(edge.target)
            if node:
                result.append(node)

        return result


