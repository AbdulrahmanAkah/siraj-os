from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.selection.claim_selector import ClaimSelector


def test_selector_ranks_uncontradicted_claims_ahead_of_conflicted_claims():
    graph = KnowledgeRepository().ingest_text(
        "Muhammad was born in 570. Muhammad was born in 571. "
        "Muhammad traveled to Makkah in 610. The source is History Book."
    )
    selector = ClaimSelector(HistoricalReasoner(KnowledgeRetriever(graph)))

    ranked = selector.rank_claims()

    assert ranked == selector.rank_claims()
    assert ranked[0].score > ranked[-1].score
    assert ranked[0].claim_id == next(
        claim.id
        for claim in selector.reasoner.get_claims()
        if "traveled to" in claim.data["text"].lower()
    )
