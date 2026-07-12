from dataclasses import dataclass,field
from .graph_index import GraphIndex


@dataclass
class KnowledgeGraph:


    nodes:list=field(default_factory=list)
    edges:list=field(default_factory=list)
    relationships:list=field(default_factory=list)



    def __post_init__(self):

        self.index=GraphIndex()

        self.rebuild_index()



    def rebuild_index(self):

        self.index.build(self)



    def add_node(self,node):

        self.nodes.append(node)



    def add_edge(self,edge):

        self.edges.append(edge)



    def add_relationship(self,r):

        self.relationships.append(r)



    def refresh(self):

        self.rebuild_index()



    def get_node(self,node_id):

        self.refresh()

        return self.index.get_node(node_id)



    def find_by_type(self,t):

        self.refresh()

        return self.index.find_by_type(t)



    def get_nodes_by_type(self,node_type):

        return self.find_by_type(node_type)



    def outgoing(self,node_id):

        return self.index.get_outgoing(node_id)



    def to_dict(self):

        return {

        "nodes":[
            x.to_dict()
            for x in self.nodes
        ],

        "edges":[
            x.to_dict()
            for x in self.edges
        ],

        "relationships":[
            x.to_dict()
            for x in self.relationships
        ]

        }

