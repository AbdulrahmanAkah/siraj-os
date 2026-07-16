import pytest

from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.selection.claim_selector import ClaimSelector


def test_selector_requires_reasoning_and_does_not_mutate_the_graph():
    graph = KnowledgeRepository().ingest_text(
        "Muhammad traveled to Makkah in 610. The source is History Book."
    )
    before = graph.to_dict()
    reasoner = HistoricalReasoner(KnowledgeRetriever(graph))

    with pytest.raises(TypeError):
        ClaimSelector(reasoner.retriever)

    selector = ClaimSelector(reasoner)
    selector.rank_claims()

    assert not hasattr(selector, "graph")
    assert graph.to_dict() == before
