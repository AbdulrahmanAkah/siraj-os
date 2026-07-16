from src.application.events.event_engine import EventEngine
from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.repository.persistent_knowledge_repository import PersistentKnowledgeRepository
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.selection.claim_selector import ClaimSelector


def test_timeline_builds_after_repository_reload(tmp_path):
    repository = PersistentKnowledgeRepository(tmp_path / "repository")
    first = KnowledgeRepository().ingest_text(
        "Muhammad traveled to Makkah in 610. The source is History Book A."
    )
    second = KnowledgeRepository().ingest_text(
        "Ali traveled to Makkah in 620. The source is History Book B."
    )
    repository.save(first)
    repository.save(repository.merge(second))

    engine = EventEngine(
        ClaimSelector(HistoricalReasoner(KnowledgeRetriever.from_repository(repository)))
    )
    timeline = engine.build_timeline()

    assert len(timeline.ordered_event_ids) == 2
    assert not timeline.unplaced_event_ids
