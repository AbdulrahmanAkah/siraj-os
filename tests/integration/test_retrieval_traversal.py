from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever


def test_retrieval_traverses_edges_without_graph_access():
    graph = KnowledgeRepository().ingest_text(
        "Muhammad traveled to Makkah in 610. The source is History Book."
    )
    retriever = KnowledgeRetriever(graph)

    outgoing = retriever.get_outgoing("muhammad")
    incoming = retriever.get_incoming("makkah")
    relationships = retriever.get_relationships("muhammad")
    neighbors = retriever.get_neighbors("muhammad")

    assert any(edge.relation == "traveled_to" and edge.target == "makkah" for edge in outgoing)
    assert any(edge.relation == "traveled_to" and edge.source == "muhammad" for edge in incoming)
    assert {edge.relationship_id for edge in relationships} == {
        edge.relationship_id for edge in outgoing
    }
    assert [node.id for node in neighbors] == ["makkah"]
    assert retriever.traverse("muhammad")["node"].id == "muhammad"
