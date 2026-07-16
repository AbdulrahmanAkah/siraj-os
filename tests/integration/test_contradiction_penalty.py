from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.selection.claim_selector import ClaimSelector


def test_selector_applies_a_penalty_to_potentially_contradicted_claims():
    graph = KnowledgeRepository().ingest_text(
        "Muhammad was born in 570. Muhammad was born in 571. "
        "The source is History Book."
    )
    selector = ClaimSelector(HistoricalReasoner(KnowledgeRetriever(graph)))

    scores = selector.rank_claims()

    assert all(score.contradiction_penalty == 0.30 for score in scores)
    assert all(score.score < selector.REJECTION_THRESHOLD for score in scores)
