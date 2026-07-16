from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.repository.persistent_knowledge_repository import PersistentKnowledgeRepository
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever


def test_retrieval_loads_indexes_from_a_saved_repository(tmp_path):
    graph = KnowledgeRepository().ingest_text(
        "Muhammad traveled to Makkah in 610. The source is History Book.",
        document_title="History excerpt",
    )
    repository = PersistentKnowledgeRepository(tmp_path / "repository")
    repository.save(graph)

    retriever = KnowledgeRetriever.from_repository(repository)
    claim = next(iter(retriever.index.claims_by_id.values()))

    assert retriever.find_node("muhammad").type == "PERSON"
    assert retriever.get_claim_evidence(claim.id)
    assert retriever.get_claim_sources(claim.id)
    assert retriever.get_claim_provenance(claim.id)["documents"]
