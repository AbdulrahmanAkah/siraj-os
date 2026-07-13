from src.application.knowledge.knowledge_repository import KnowledgeRepository


def _normalized(value):
    return str(value or "").strip().lower().lstrip("\ufeff")


def _print_final_graph(graph):
    print("\n=== FINAL GRAPH NODES ===")
    for node in graph.nodes:
        data = node.data if isinstance(node.data, dict) else {}
        name = data.get("name") or data.get("title") or data.get("text") or data.get("value")
        print(f"{node.id} | {node.type} | {name}")

    print("\n=== FINAL GRAPH EDGES ===")
    for edge in graph.edges:
        print(f"{edge.source} | {edge.relation} | {edge.target}")
        if edge.metadata.get("date"):
            print(f"date: {edge.metadata['date']}")


def test_bom_prefixed_relationship_endpoint_reuses_person_node():
    graph = KnowledgeRepository().ingest_text(
        "\ufeffMuhammad traveled to Makkah in 610."
    )

    _print_final_graph(graph)

    persons = [
        node
        for node in graph.nodes
        if node.type == "PERSON" and _normalized(node.data.get("name")) == "muhammad"
    ]
    assert len(persons) == 1

    duplicate_entities = [
        node
        for node in graph.nodes
        if node.type == "ENTITY" and _normalized(node.data.get("name")) == "muhammad"
    ]
    assert not duplicate_entities, "BOM-prefixed Muhammad created a duplicate ENTITY node"

    assert any(
        edge.source == "muhammad"
        and edge.relation == "traveled_to"
        and edge.target == "makkah"
        and edge.metadata.get("date") == "610"
        for edge in graph.edges
    )
