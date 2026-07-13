from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.selection.claim_selector import ClaimSelector


def test_selector_generates_deterministic_component_scores():
    graph = KnowledgeRepository().ingest_text(
        "Muhammad traveled to Makkah in 610. The source is History Book."
    )
    selector = ClaimSelector(HistoricalReasoner(KnowledgeRetriever(graph)))
    claim_id = selector.reasoner.get_claims()[0].id

    score = selector.evaluate_claim(claim_id)

    assert score.claim_id == claim_id
    assert score.support_score == 0.234
    assert score.evidence_score == 0.125
    assert score.source_score == 0.125
    assert score.contradiction_penalty == 0.0
    assert score.score == 0.484
