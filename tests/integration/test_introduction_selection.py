from src.application.documentary_planning.documentary_planner import DocumentaryPlanner
from src.application.events.event_engine import EventEngine
from src.application.events.models import HistoricalEvent, HistoricalTimeline
from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.selection.claim_selector import ClaimSelector


def test_introduction_selects_the_highest_importance_event():
    graph = KnowledgeRepository().ingest_text("Muhammad traveled to Makkah in 610.")
    planner = DocumentaryPlanner(EventEngine(ClaimSelector(HistoricalReasoner(KnowledgeRetriever(graph)))))
    events = [
        HistoricalEvent("event_low", "Low", confidence=0.4, year=610),
        HistoricalEvent(
            "event_high",
            "High",
            claim_ids=["claim"],
            evidence_ids=["evidence"],
            source_ids=["source"],
            confidence=0.8,
            year=620,
        ),
    ]
    timeline = HistoricalTimeline("timeline_test", events, [event.event_id for event in events])

    assert planner.get_introduction(timeline).event_ids == ["event_high"]
