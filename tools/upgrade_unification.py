from pathlib import Path


files = {

"src/application/knowledge/canonicalizer.py":
r'''
import re


class Canonicalizer:


    @staticmethod
    def normalize_text(text):

        if not text:
            return ""

        text = text.strip()

        text = re.sub(
            r"[.,;:!?]+$",
            "",
            text
        )

        text = re.sub(
            r"\s+",
            " ",
            text
        )

        return text.lower()



    @staticmethod
    def canonical_name(text):

        text = Canonicalizer.normalize_text(text)

        aliases = {

            "prophet muhammad": "muhammad",
            "the prophet": "muhammad",
            "muhammad": "muhammad",

            "the muslims": "muslims",
            "muslim army": "muslim army",

            "quraysh": "quraysh",

            "madinah": "madinah",
            "medina": "madinah",

            "badr": "badr",
        }


        return aliases.get(
            text,
            text
        )
''',


"src/domain/knowledge_graph/graph_index.py":
r'''
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
''',


"src/domain/knowledge_graph/knowledge_graph.py":
r'''
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
'''
}



for path,content in files.items():

    p=Path(path)

    p.write_text(
        content.strip(),
        encoding="utf-8"
    )


print("UNIFICATION PATCH COMPLETE")