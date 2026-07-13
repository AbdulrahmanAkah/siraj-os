from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever


def test_reasoner_builds_a_cluster_for_deterministically_related_claims():
    graph = KnowledgeRepository().ingest_text(
        "Muhammad was born in Mecca. The Prophet Muhammad was born in Mecca. "
        "The source is History Book."
    )
    reasoner = HistoricalReasoner(KnowledgeRetriever(graph))
    claims = reasoner.retriever.get_claims()

    cluster = reasoner.build_claim_cluster(claims[0].id)

    assert len(cluster.claim_ids) == 2
    assert set(cluster.claim_ids) == {claim.id for claim in claims}
    assert len(cluster.evidence_ids) == 2
    assert cluster.document_ids
    assert cluster.source_ids
