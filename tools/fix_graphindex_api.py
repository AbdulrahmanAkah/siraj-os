from pathlib import Path


path = Path(
"src/domain/knowledge_graph/graph_index.py"
)


text = path.read_text(
    encoding="utf-8"
)


patch = """


    def build(self, graph):

        self.nodes_by_id.clear()
        self.nodes_by_type.clear()

        self.outgoing.clear()
        self.incoming.clear()

        self.relationships_by_predicate.clear()


        for node in graph.nodes:
            self.add_node(node)


        for edge in graph.edges:
            self.add_edge(edge)


        for rel in graph.relationships:
            self.add_relationship(rel)



    def get_nodes_by_type(self, node_type):

        return self.find_by_type(node_type)



    def get_outgoing(self, node_id):

        return self.outgoing.get(node_id, [])



    def get_incoming(self, node_id):

        return self.incoming.get(node_id, [])


"""


if "def build(self, graph)" not in text:

    text += patch


path.write_text(
    text,
    encoding="utf-8"
)


print(
"GRAPH INDEX API PATCHED"
)