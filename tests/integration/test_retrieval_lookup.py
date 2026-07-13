from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever


def _retriever():
    graph = KnowledgeRepository().ingest_text(
        "Muhammad traveled to Makkah in 610. The source is History Book.",
        document_title="History excerpt",
    )
    return KnowledgeRetriever(graph)


def test_retrieval_lookup_uses_canonical_stable_ids():
    retriever = _retriever()
    claim = next(iter(retriever.index.claims_by_id.values()))
    source = next(iter(retriever.index.sources_by_id.values()))
    document = next(iter(retriever.index.documents_by_id.values()))
    evidence = next(iter(retriever.index.evidence_by_id.values()))

    assert retriever.find_node("muhammad").type == "PERSON"
    assert retriever.find_claim(claim.id) is claim
    assert retriever.find_source(source.id) is source
    assert retriever.find_document(document.id) is document
    assert retriever.find_evidence(evidence.id) is evidence
    assert retriever.lookup(claim.id) is claim
    assert retriever.find_entity("Muhammad").id == "muhammad"
    assert [node.id for node in retriever.find_people("Muhammad")] == ["muhammad"]
    assert [node.id for node in retriever.find_locations("Makkah")] == ["makkah"]
