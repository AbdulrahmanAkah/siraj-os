from src.application.documentary_planning.documentary_planner import DocumentaryPlanner
from src.application.events.event_engine import EventEngine
from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.repository.persistent_knowledge_repository import PersistentKnowledgeRepository
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.selection.claim_selector import ClaimSelector


def test_documentary_plan_builds_after_repository_reload(tmp_path):
    repository = PersistentKnowledgeRepository(tmp_path / "repository")
    repository.save(
        KnowledgeRepository().ingest_text(
            "Muhammad traveled to Makkah in 610. Ali traveled to Makkah in 620. "
            "The source is History Book."
        )
    )
    planner = DocumentaryPlanner(
        EventEngine(
            ClaimSelector(HistoricalReasoner(KnowledgeRetriever.from_repository(repository)))
        )
    )

    plan = planner.build_documentary_plan(title="Reloaded History")

    assert plan.selected_event_ids
    assert plan.estimated_runtime > 0
