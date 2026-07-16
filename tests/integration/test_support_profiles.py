from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever


def test_support_profile_counts_persisted_provenance():
    graph = KnowledgeRepository().ingest_text(
        "Muhammad traveled to Makkah in 610. The source is History Book."
    )
    reasoner = HistoricalReasoner(KnowledgeRetriever(graph))
    claim = reasoner.retriever.get_claims()[0]

    profile = reasoner.get_support_profile(claim.id)

    assert profile.claim_id == claim.id
    assert profile.evidence_count == 1
    assert profile.source_count == 1
    assert profile.document_count == 1
    assert profile.confidence_score == 0.78
    assert "evidence_count=1" in profile.confidence_signals
