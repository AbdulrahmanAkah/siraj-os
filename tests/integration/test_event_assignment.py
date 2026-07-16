from src.application.documentary_planning.documentary_planner import DocumentaryPlanner
from src.application.events.event_engine import EventEngine
from src.application.events.models import HistoricalEvent, HistoricalTimeline
from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.selection.claim_selector import ClaimSelector


def test_assign_event_returns_its_deterministic_section():
    graph = KnowledgeRepository().ingest_text("Muhammad traveled to Makkah in 610.")
    planner = DocumentaryPlanner(EventEngine(ClaimSelector(HistoricalReasoner(KnowledgeRetriever(graph)))))
    events = [
        HistoricalEvent("event_a", "A", confidence=0.9, year=610),
        HistoricalEvent("event_b", "B", confidence=0.5, year=620),
        HistoricalEvent("event_c", "C", confidence=0.6, year=630),
    ]
    timeline = HistoricalTimeline("timeline_test", events, [event.event_id for event in events])

    assert planner.assign_event("event_b", timeline).section_id == "chapter_1"
    assert planner.assign_event("missing", timeline) is None
