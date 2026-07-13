from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.repository.persistent_knowledge_repository import PersistentKnowledgeRepository
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.selection.claim_selector import ClaimSelector


def test_selection_works_after_repository_reload(tmp_path):
    graph = KnowledgeRepository().ingest_text(
        "Muhammad was born in 570. Muhammad was born in 571. "
        "Muhammad traveled to Makkah in 610. The source is History Book."
    )
    repository = PersistentKnowledgeRepository(tmp_path / "repository")
    repository.save(graph)

    selector = ClaimSelector(
        HistoricalReasoner(KnowledgeRetriever.from_repository(repository))
    )

    assert selector.select_top_claims(1)
    assert len(selector.rank_claims()) == 3
    assert selector.build_selection_profile(selector.rank_claims()[0].claim_id)
