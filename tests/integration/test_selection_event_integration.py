import pytest

from src.application.events.event_engine import EventEngine
from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.selection.claim_selector import ClaimSelector


def test_event_engine_requires_selection_and_does_not_mutate_the_graph():
    graph = KnowledgeRepository().ingest_text(
        "Muhammad traveled to Makkah in 610. The source is History Book."
    )
    before = graph.to_dict()
    selector = ClaimSelector(HistoricalReasoner(KnowledgeRetriever(graph)))

    with pytest.raises(TypeError):
        EventEngine(selector.reasoner)

    engine = EventEngine(selector)
    assert engine.build_events()
    assert not hasattr(engine, "graph")
    assert graph.to_dict() == before
