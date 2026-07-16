import json

from src.application.knowledge.knowledge_repository import KnowledgeRepository


def _provenance_graph():
    return KnowledgeRepository().ingest_text(
        "Muhammad traveled to Makkah in 610. The source is History Book.",
        document_title="History excerpt",
    )


def test_claim_provenance_survives_graph_serialization():
    graph = _provenance_graph()
    claim = next(node for node in graph.nodes if node.type == "CLAIM")

    assert claim.data["claim_id"] == claim.id
    assert claim.data["source_ids"]
    assert claim.data["evidence_ids"]
    assert claim.data["confidence"] == 0.8

    serialized = json.loads(json.dumps(graph.to_dict()))
    serialized_claim = next(node for node in serialized["nodes"] if node["id"] == claim.id)
    assert serialized_claim["data"]["evidence_ids"] == claim.data["evidence_ids"]


def test_claim_evidence_source_path_is_reconstructable():
    graph = _provenance_graph()
    claim = next(node for node in graph.nodes if node.type == "CLAIM")
    evidence_id = claim.data["evidence_ids"][0]
    source_id = claim.data["source_ids"][0]

    assert any(
        edge.source == claim.id and edge.target == evidence_id and edge.relation == "supported_by"
        for edge in graph.edges
    )
    evidence = graph.get_node(evidence_id)
    assert evidence.type == "EVIDENCE"
    document_edge = next(
        edge for edge in graph.edges if edge.source == evidence_id and edge.relation == "located_in"
    )
    assert graph.get_node(document_edge.target).type == "DOCUMENT"
    assert any(
        edge.source == document_edge.target and edge.target == source_id and edge.relation == "originates_from"
        for edge in graph.edges
    )


def test_provenance_does_not_break_entity_resolution():
    graph = _provenance_graph()

    assert any(node.id == "muhammad" and node.type == "PERSON" for node in graph.nodes)
    assert not any(node.id == "muhammad" and node.type == "ENTITY" for node in graph.nodes)
    assert any(
        edge.source == "muhammad" and edge.target == "makkah" and edge.relation == "traveled_to"
        for edge in graph.edges
    )
