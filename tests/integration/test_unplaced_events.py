from src.application.events.event_engine import EventEngine
from src.application.events.models import HistoricalEvent
from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.selection.claim_selector import ClaimSelector


def test_unknown_time_events_are_kept_unplaced_in_stable_order():
    graph = KnowledgeRepository().ingest_text("Muhammad traveled to Makkah in 610.")
    engine = EventEngine(ClaimSelector(HistoricalReasoner(KnowledgeRetriever(graph))))
    events = [
        HistoricalEvent(event_id="event_b", title="Unknown B"),
        HistoricalEvent(event_id="event_a", title="Unknown A"),
        HistoricalEvent(event_id="event_dated", title="Dated", year=610),
    ]

    timeline = engine.build_timeline(events)

    assert timeline.ordered_event_ids == ["event_dated"]
    assert timeline.unplaced_event_ids == ["event_a", "event_b"]
    assert [event.event_id for event in engine.get_unplaced_events(events)] == [
        "event_a",
        "event_b",
    ]
