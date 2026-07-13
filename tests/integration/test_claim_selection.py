from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.selection.claim_selector import ClaimSelector


def test_selector_returns_the_requested_top_claims_and_rejects_weak_ones():
    graph = KnowledgeRepository().ingest_text(
        "Muhammad was born in 570. Muhammad was born in 571. "
        "Muhammad traveled to Makkah in 610. The source is History Book."
    )
    selector = ClaimSelector(HistoricalReasoner(KnowledgeRetriever(graph)))

    selected = selector.select_top_claims(1)
    rejected = selector.reject_claims()

    assert len(selected) == 1
    assert selected == selector.select_claims(1)
    assert len(rejected) == 2
    assert all(score.score < selector.REJECTION_THRESHOLD for score in rejected)
