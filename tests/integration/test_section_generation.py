from src.application.documentary_planning.documentary_planner import DocumentaryPlanner
from src.application.events.event_engine import EventEngine
from src.application.events.models import HistoricalEvent, HistoricalTimeline
from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.selection.claim_selector import ClaimSelector


def test_sections_keep_core_events_in_timeline_order_without_duplicates():
    graph = KnowledgeRepository().ingest_text("Muhammad traveled to Makkah in 610.")
    planner = DocumentaryPlanner(EventEngine(ClaimSelector(HistoricalReasoner(KnowledgeRetriever(graph)))))
    events = [
        HistoricalEvent(f"event_{index}", str(index), confidence=0.5, year=600 + index)
        for index in range(1, 7)
    ]
    timeline = HistoricalTimeline("timeline_test", events, [event.event_id for event in events])

    sections = planner.build_sections(timeline)
    assigned = [event_id for section in sections for event_id in section.event_ids]
    core_ids = [
        event_id
        for section in sections
        if section.section_id.startswith("chapter_")
        for event_id in section.event_ids
    ]

    assert assigned == list(dict.fromkeys(assigned))
    assert set(assigned) == {event.event_id for event in events}
    assert core_ids == sorted(core_ids)
