import pytest

from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever


def test_reasoner_requires_retrieval_and_does_not_mutate_the_graph():
    graph = KnowledgeRepository().ingest_text(
        "Muhammad traveled to Makkah in 610. The source is History Book."
    )
    before = graph.to_dict()

    with pytest.raises(TypeError):
        HistoricalReasoner(graph)

    reasoner = HistoricalReasoner(KnowledgeRetriever(graph))
    claim = reasoner.retriever.get_claims()[0]
    analysis = reasoner.analyze_claim(claim.id)

    assert not hasattr(reasoner, "graph")
    assert analysis["claim"].id == claim.id
    assert graph.to_dict() == before
