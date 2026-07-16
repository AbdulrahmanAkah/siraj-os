from src.domain.knowledge_graph.knowledge_graph import KnowledgeGraph
from src.domain.knowledge_graph.knowledge_graph_query import KnowledgeGraphQuery
from src.domain.knowledge_graph.knowledge_node import KnowledgeNode
from src.domain.knowledge_graph.knowledge_edge import KnowledgeEdge

graph = KnowledgeGraph()

graph.add_node(
    KnowledgeNode(
        id="person:muhammad",
        type="PERSON",
        data={"name": "Muhammad"},
    )
)

graph.add_node(
    KnowledgeNode(
        id="event:badr",
        type="EVENT",
        data={"title": "Battle of Badr"},
    )
)

graph.add_edge(
    KnowledgeEdge(
        source="person:muhammad",
        target="event:badr",
        relation="participated_in",
    )
)

query = KnowledgeGraphQuery(graph)

assert query.node("person:muhammad").data["name"] == "Muhammad"
assert len(query.people()) == 1
assert len(query.events()) == 1
assert len(query.outgoing("person:muhammad")) == 1
assert len(query.incoming("event:badr")) == 1

print("KnowledgeGraphQuery OK")
print([n.to_dict() for n in query.people()])
print([n.to_dict() for n in query.events()])
print([e.to_dict() for e in query.outgoing("person:muhammad")])


