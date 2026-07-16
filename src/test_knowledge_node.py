from src.domain.knowledge_graph.knowledge_node import KnowledgeNode

node = KnowledgeNode(
    id="person:muhammad",
    type="PERSON",
    data={
        "name":"Muhammad"
    }
)

print(node.to_dict())

assert node.id == "person:muhammad"
assert node.type == "PERSON"
assert node.data["name"] == "Muhammad"


