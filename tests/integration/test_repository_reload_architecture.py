from src.application.documentary_planning.documentary_planner import DocumentaryPlanner
from src.application.events.event_engine import EventEngine
from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.narrative_architecture.narrative_architect import NarrativeArchitect
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.repository.persistent_knowledge_repository import PersistentKnowledgeRepository
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.selection.claim_selector import ClaimSelector


def test_narrative_architecture_builds_after_repository_reload(tmp_path):
    repository = PersistentKnowledgeRepository(tmp_path / "repository")
    repository.save(
        KnowledgeRepository().ingest_text(
            "Muhammad traveled to Makkah in 610. Ali traveled to Makkah in 620. "
            "The source is History Book."
        )
    )
    architect = NarrativeArchitect(
        DocumentaryPlanner(
            EventEngine(
                ClaimSelector(
                    HistoricalReasoner(KnowledgeRetriever.from_repository(repository))
                )
            )
        )
    )

    architecture = architect.build_narrative_architecture()

    assert architecture.beats
    assert architect.validate_structure(architecture)
