from src.application.documentary_planning.documentary_planner import DocumentaryPlanner
from src.application.events.event_engine import EventEngine
from src.application.events.models import HistoricalEvent, HistoricalTimeline
from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.selection.claim_selector import ClaimSelector


def _planner():
    graph = KnowledgeRepository().ingest_text("Muhammad traveled to Makkah in 610.")
    return DocumentaryPlanner(EventEngine(ClaimSelector(HistoricalReasoner(KnowledgeRetriever(graph)))))


def test_documentary_planner_builds_a_complete_deterministic_plan():
    events = [
        HistoricalEvent(f"event_{year}", str(year), confidence=0.7, year=year)
        for year in (570, 580, 590, 600, 610)
    ]
    timeline = HistoricalTimeline(
        "timeline_test", events, [event.event_id for event in events]
    )

    plan = _planner().build_documentary_plan(timeline, title="Muhammad")

    assert plan.plan_id.startswith("plan_")
    assert plan.title == "Muhammad"
    assert [section.title for section in plan.sections] == [
        "Introduction",
        "Chapter 1",
        "Chapter 2",
        "Chapter 3",
        "Conclusion",
    ]
    assert sorted(plan.selected_event_ids) == sorted(timeline.ordered_event_ids)
