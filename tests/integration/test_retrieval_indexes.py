from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever


def test_retrieval_indexes_back_constant_time_identifier_lookups():
    graph = KnowledgeRepository().ingest_text(
        "Muhammad traveled to Makkah in 610. The source is History Book."
    )
    original_graph = graph.to_dict()
    retriever = KnowledgeRetriever(graph)
    claim = next(iter(retriever.index.claims_by_id.values()))
    source = next(iter(retriever.index.sources_by_id.values()))

    assert retriever.index.nodes_by_id[claim.id] is claim
    assert retriever.index.claims_by_id[claim.id] is claim
    assert retriever.index.sources_by_id[source.id] is source
    assert retriever.index.edges_by_id
    assert retriever.find_node(claim.id) is retriever.index.nodes_by_id[claim.id]
    assert retriever.find_claim(claim.id) is retriever.index.claims_by_id[claim.id]
    assert graph.to_dict() == original_graph
