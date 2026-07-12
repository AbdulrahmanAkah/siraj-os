from src.domain.knowledge_graph.knowledge_graph import KnowledgeGraph


class KnowledgeGraphQuery:
    def __init__(self, graph: KnowledgeGraph):
        self.graph = graph

    def node(self, node_id: str):
        return self.graph.get_node(node_id)

    def people(self):
        return self.graph.get_nodes_by_type("PERSON")

    def events(self):
        return self.graph.get_nodes_by_type("EVENT")

    def timeline(self):
        return self.graph.get_nodes_by_type("TIMELINE_EVENT")

    def statistics(self):
        return self.graph.get_nodes_by_type("STATISTIC")

    def relationships(self):
        return self.graph.get_nodes_by_type("RELATIONSHIP")

    def outgoing(self, node_id: str):
        return self.graph.outgoing(node_id)

    def incoming(self, node_id: str):
        return self.graph.incoming(node_id)


