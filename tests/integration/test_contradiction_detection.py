from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever


def test_reasoner_detects_numeric_conflicts_for_the_same_claim_pattern():
    graph = KnowledgeRepository().ingest_text(
        "Muhammad was born in 570. Muhammad was born in 571. "
        "The source is History Book."
    )
    reasoner = HistoricalReasoner(KnowledgeRetriever(graph))
    claims = reasoner.retriever.get_claims()

    contradictions = reasoner.find_contradictions()

    assert len(contradictions) == 1
    contradiction = contradictions[0]
    assert {contradiction.claim_a, contradiction.claim_b} == {claim.id for claim in claims}
    assert "conflicting numeric values" in contradiction.reason
    assert contradiction.confidence == 0.75
