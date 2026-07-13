from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever


def test_claim_provenance_is_retrievable_as_a_complete_path():
    graph = KnowledgeRepository().ingest_text(
        "Muhammad traveled to Makkah in 610. The source is History Book.",
        document_title="History excerpt",
    )
    retriever = KnowledgeRetriever(graph)
    claim = next(iter(retriever.index.claims_by_id.values()))

    provenance = retriever.get_claim_provenance(claim.id)
    evidence = provenance["evidence"][0]
    document = retriever.get_evidence_document(evidence.id)
    source = retriever.get_document_source(document.id)

    assert provenance["claim"] is claim
    assert evidence.id in claim.data["evidence_ids"]
    assert document.id == evidence.data["document_id"]
    assert source.id == document.data["source_id"]
    assert source in provenance["sources"]
