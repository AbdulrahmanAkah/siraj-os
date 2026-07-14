from src.application.documentary_planning.documentary_planner import DocumentaryPlanner
from src.application.documentary_planning.models import DocumentarySection
from src.application.events.event_engine import EventEngine
from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.selection.claim_selector import ClaimSelector


def test_runtime_estimation_is_the_sum_of_section_durations():
    graph = KnowledgeRepository().ingest_text("Muhammad traveled to Makkah in 610.")
    planner = DocumentaryPlanner(EventEngine(ClaimSelector(HistoricalReasoner(KnowledgeRetriever(graph)))))
    sections = [
        DocumentarySection("introduction", "Introduction", ["event_a"], estimated_duration=1.75),
        DocumentarySection("chapter_1", "Chapter 1", ["event_b", "event_c"], estimated_duration=2.5),
    ]

    assert planner.estimate_runtime(sections) == 4.25
