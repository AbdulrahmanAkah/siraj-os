from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.repository.persistent_knowledge_repository import PersistentKnowledgeRepository
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever


def test_reasoning_works_after_repository_reload(tmp_path):
    graph = KnowledgeRepository().ingest_text(
        "Muhammad was born in 570. Muhammad was born in 571. "
        "The source is History Book."
    )
    repository = PersistentKnowledgeRepository(tmp_path / "repository")
    repository.save(graph)

    reasoner = HistoricalReasoner(KnowledgeRetriever.from_repository(repository))
    claim = reasoner.retriever.get_claims()[0]

    assert reasoner.get_support_profile(claim.id).evidence_count == 1
    assert len(reasoner.find_contradictions()) == 1
    assert reasoner.build_claim_cluster(claim.id).source_ids
