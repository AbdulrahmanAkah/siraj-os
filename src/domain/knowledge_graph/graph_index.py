from collections import defaultdict


class GraphIndex:


    def __init__(self):

        self.nodes_by_id={}
        self.nodes_by_type=defaultdict(list)
        self.outgoing=defaultdict(list)
        self.incoming=defaultdict(list)
        self.relationships_by_predicate=defaultdict(list)



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



    def add_node(self,node):

        self.nodes_by_id[node.id]=node
        self.nodes_by_type[node.type].append(node)



    def add_edge(self,edge):

        self.outgoing[
            edge.source
        ].append(edge)

        self.incoming[
            edge.target
        ].append(edge)



    def add_relationship(self,relationship):

        self.relationships_by_predicate[
            relationship.predicate
        ].append(relationship)



    def get_node(self,node_id):

        return self.nodes_by_id.get(node_id)



    def find_by_type(self,node_type):

        return self.nodes_by_type.get(
            node_type,
            []
        )


    def get_nodes_by_type(self, node_type):
        return self.find_by_type(node_type)




    def get_outgoing(self, node_id):
        return self.outgoing.get(node_id, [])




    def get_incoming(self, node_id):
        return self.incoming.get(node_id, [])



