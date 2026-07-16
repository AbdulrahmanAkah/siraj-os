from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.repository.persistent_knowledge_repository import PersistentKnowledgeRepository


def test_merge_reuses_duplicate_provenance_identities(tmp_path):
    text = "Muhammad traveled to Makkah in 610. The source is History Book."
    first_graph = KnowledgeRepository().ingest_text(text, document_title="History excerpt")
    second_graph = KnowledgeRepository().ingest_text(text, document_title="History excerpt")
    repository = PersistentKnowledgeRepository(tmp_path / "repository")
    repository.save(first_graph)
    merged = repository.merge(second_graph)
    repository.save(merged)

    for node_type in ("SOURCE", "DOCUMENT", "EVIDENCE", "CLAIM"):
        original_ids = {node.id for node in first_graph.nodes if node.type == node_type}
        merged_ids = {node.id for node in merged.nodes if node.type == node_type}
        assert merged_ids == original_ids
        assert len(merged_ids) == len([node for node in merged.nodes if node.type == node_type])

    assert len({edge.relationship_id for edge in merged.edges}) == len(merged.edges)
