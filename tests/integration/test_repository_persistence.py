from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.repository.persistent_knowledge_repository import PersistentKnowledgeRepository
from src.domain.knowledge_objects.relationship import Relationship


def test_repository_save_load_round_trip_preserves_provenance(tmp_path):
    graph = KnowledgeRepository().ingest_text(
        "Muhammad traveled to Makkah in 610. The source is History Book.",
        document_title="History excerpt",
    )
    graph.add_relationship(
        Relationship(subject="Muhammad", predicate="traveled_to", object="Makkah")
    )
    repository = PersistentKnowledgeRepository(tmp_path / "repository")
    repository.save(graph)

    assert repository.exists()
    for filename in (
        "sources.json",
        "documents.json",
        "evidence.json",
        "claims.json",
        "graph.json",
        "metadata.json",
    ):
        assert (repository.path / filename).exists()

    loaded = repository.load()
    assert {node.id for node in loaded.nodes} == {node.id for node in graph.nodes}
    assert {edge.relationship_id for edge in loaded.edges} == {
        edge.relationship_id for edge in graph.edges
    }

    claim = next(node for node in loaded.nodes if node.type == "CLAIM")
    evidence_id = claim.data["evidence_ids"][0]
    assert repository.get_by_id(claim.id) is not None
    assert any(
        edge.source == claim.id and edge.target == evidence_id and edge.relation == "supported_by"
        for edge in loaded.edges
    )
    assert len(loaded.relationships) == 1
    assert loaded.relationships[0].predicate == "traveled_to"
