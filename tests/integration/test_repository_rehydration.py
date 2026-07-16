from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.repository.persistent_knowledge_repository import PersistentKnowledgeRepository


def test_loaded_repository_can_continue_growing_and_save_again(tmp_path):
    repository = PersistentKnowledgeRepository(tmp_path / "repository")
    first_graph = KnowledgeRepository().ingest_text(
        "Muhammad traveled to Makkah in 610. The source is History Book.",
        document_title="History excerpt A",
    )
    repository.save(first_graph)

    second_graph = KnowledgeRepository().ingest_text(
        "Ali traveled to Makkah in 620. The source is Chronicle B.",
        document_title="History excerpt B",
    )
    repository.save(repository.merge(second_graph))
    rehydrated = repository.load()

    assert any(node.id == "muhammad" for node in rehydrated.nodes)
    assert any(node.id == "ali" for node in rehydrated.nodes)
    assert len([node for node in rehydrated.nodes if node.type == "DOCUMENT"]) == 2
    assert len([node for node in rehydrated.nodes if node.type == "CLAIM"]) == 2
    assert any(edge.relation == "supported_by" for edge in rehydrated.edges)
