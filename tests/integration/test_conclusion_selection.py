from src.application.documentary_planning.documentary_planner import DocumentaryPlanner
from src.application.events.event_engine import EventEngine
from src.application.events.models import HistoricalEvent, HistoricalTimeline
from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.selection.claim_selector import ClaimSelector


def test_conclusion_selects_the_latest_remaining_timeline_event():
    graph = KnowledgeRepository().ingest_text("Muhammad traveled to Makkah in 610.")
    planner = DocumentaryPlanner(EventEngine(ClaimSelector(HistoricalReasoner(KnowledgeRetriever(graph)))))
    events = [
        HistoricalEvent("event_open", "Open", confidence=0.9, year=610),
        HistoricalEvent("event_middle", "Middle", confidence=0.5, year=620),
        HistoricalEvent("event_outcome", "Outcome and legacy", confidence=0.6, year=630),
    ]
    timeline = HistoricalTimeline("timeline_test", events, [event.event_id for event in events])

    assert planner.get_conclusion(timeline).event_ids == ["event_outcome"]
