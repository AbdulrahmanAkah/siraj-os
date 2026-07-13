from src.application.knowledge.knowledge_repository import KnowledgeRepository


def test_bom_is_removed_from_stored_claim_and_timeline_text():
    graph = KnowledgeRepository().ingest_text(
        "\ufeffMuhammad traveled to Makkah in 610."
    )

    claims = [node for node in graph.nodes if node.type == "CLAIM"]
    timeline = [node for node in graph.nodes if node.type == "TIMELINE_EVENT"]

    print("\n=== STORED TEXT ===")
    for claim in claims:
        print(f"claim: {claim.data['text']}")
    for event in timeline:
        print(f"timeline: {event.data['title']}")

    assert claims
    assert timeline
    assert claims[0].data["text"].startswith("Muhammad")
    assert timeline[0].data["title"].startswith("Muhammad")
