from src.application.events.event_engine import EventEngine
from src.application.events.models import HistoricalEvent
from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.selection.claim_selector import ClaimSelector


def test_timeline_orders_years_dates_and_equal_values_stably():
    graph = KnowledgeRepository().ingest_text("Muhammad traveled to Makkah in 610.")
    engine = EventEngine(ClaimSelector(HistoricalReasoner(KnowledgeRetriever(graph))))
    events = [
        HistoricalEvent(event_id="event_year_624", title="Year", year=624),
        HistoricalEvent(event_id="event_date_b", title="Date B", date="624-03-12", year=624),
        HistoricalEvent(event_id="event_date_a", title="Date A", date="624-03-10", year=624),
        HistoricalEvent(event_id="event_year_570", title="Early", year=570),
        HistoricalEvent(event_id="event_date_same_b", title="Same B", date="625-01-01", year=625),
        HistoricalEvent(event_id="event_date_same_a", title="Same A", date="625-01-01", year=625),
    ]

    timeline = engine.build_timeline(events)

    assert timeline.ordered_event_ids == [
        "event_year_570",
        "event_date_a",
        "event_date_b",
        "event_year_624",
        "event_date_same_a",
        "event_date_same_b",
    ]
