from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.selection.claim_selector import ClaimSelector


def test_selection_profile_explains_the_final_score():
    graph = KnowledgeRepository().ingest_text(
        "Muhammad was born in 570. Muhammad was born in 571. "
        "The source is History Book."
    )
    selector = ClaimSelector(HistoricalReasoner(KnowledgeRetriever(graph)))
    claim_id = selector.reasoner.get_claims()[0].id

    profile = selector.build_selection_profile(claim_id)

    assert profile.claim_id == claim_id
    assert profile.final_score == selector.evaluate_claim(claim_id).score
    assert profile.support_summary == "evidence=1, sources=1, documents=1"
    assert profile.contradiction_summary == "potential_contradictions=1"
    assert any("contradiction penalty" in reason for reason in profile.reasons)
