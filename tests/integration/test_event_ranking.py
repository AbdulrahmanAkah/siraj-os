from src.application.events.event_engine import EventEngine
from src.application.events.models import HistoricalEvent
from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.selection.claim_selector import ClaimSelector


def test_event_ranking_is_confidence_descending_then_event_id():
    graph = KnowledgeRepository().ingest_text("Muhammad traveled to Makkah in 610.")
    engine = EventEngine(ClaimSelector(HistoricalReasoner(KnowledgeRetriever(graph))))
    events = [
        HistoricalEvent(event_id="event_b", title="B", confidence=0.8),
        HistoricalEvent(event_id="event_a", title="A", confidence=0.8),
        HistoricalEvent(event_id="event_c", title="C", confidence=0.9),
    ]

    assert [event.event_id for event in engine.rank_events(events)] == [
        "event_c",
        "event_a",
        "event_b",
    ]
