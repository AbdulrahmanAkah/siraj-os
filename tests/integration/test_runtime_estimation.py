from src.application.documentary_planning.documentary_planner import DocumentaryPlanner
from src.application.documentary_planning.models import DocumentarySection
from src.application.events.event_engine import EventEngine
from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.selection.claim_selector import ClaimSelector
from src.application.script_architecture.script_architect import ScriptArchitect


def test_runtime_estimation_is_the_sum_of_section_durations():
    graph = KnowledgeRepository().ingest_text("Muhammad traveled to Makkah in 610.")
    planner = DocumentaryPlanner(EventEngine(ClaimSelector(HistoricalReasoner(KnowledgeRetriever(graph)))))
    sections = [
        DocumentarySection("introduction", "Introduction", ["event_a"], estimated_duration=1.75),
        DocumentarySection("chapter_1", "Chapter 1", ["event_b", "event_c"], estimated_duration=2.5),
    ]

    assert planner.estimate_runtime(sections) == 4.25


def test_script_runtime_uses_segment_event_counts_and_narrative_complexity(
    narrative_architect,
    documentary_plan,
):
    architecture = narrative_architect.build_narrative_architecture(documentary_plan)
    script_architect = ScriptArchitect(narrative_architect)
    structure = script_architect.build_script_structure(architecture)

    assert structure.estimated_runtime == script_architect.estimate_runtime(
        architecture,
        structure.segments,
    )
    assert structure.estimated_runtime > structure.segment_count
