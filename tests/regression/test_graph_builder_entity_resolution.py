from src.application.knowledge.extraction_result import ExtractionResult
from src.application.knowledge.graph_builder import GraphBuilder
from src.domain.knowledge_objects.location import Location
from src.domain.knowledge_objects.person import Person
from src.domain.knowledge_objects.relationship import Relationship


def _normalized(value):
    return str(value or "").strip().lower()


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


def test_relationship_endpoint_reuses_existing_typed_node():
    extraction = ExtractionResult(
        persons=[Person(name="Muhammad")],
        locations=[Location(name="Makkah")],
        relationships=[
            Relationship(
                subject="Muhammad",
                predicate="traveled_to",
                object="Makkah in 610",
                metadata={"date": "610"},
            )
        ],
    )

    graph = GraphBuilder().build(extraction)

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
    assert not duplicate_entities, "Duplicate ENTITY Muhammad survived GraphBuilder.build()"

    assert any(
        edge.source == persons[0].id
        and edge.target == "makkah"
        and edge.relation == "traveled_to"
        and edge.metadata.get("date") == "610"
        for edge in graph.edges
    )
