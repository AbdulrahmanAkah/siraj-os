import pytest # type: ignore

from src.application.knowledge.graph_builder import GraphBuilder
from src.application.knowledge.models import ( # type: ignore
    KnowledgeNode,
    KnowledgeRelationship,
)


def normalize(value):
    return str(value).strip().lower()


def test_no_duplicate_entity_created_for_existing_person():
    """
    Regression test:
    A relationship endpoint matching an existing PERSON
    must not create a fallback ENTITY node.
    """

    nodes = [
        KnowledgeNode(
            id="muhammad",
            type="PERSON",
            data={
                "name": "Muhammad",
                "aliases": []
            }
        ),
        KnowledgeNode(
            id="makkah",
            type="LOCATION",
            data={
                "name": "Makkah"
            }
        ),
    ]

    relationships = [
        KnowledgeRelationship(
            source="Muhammad",
            target="Makkah",
            relation="traveled_to",
            metadata={
                "date": "610"
            }
        )
    ]

    builder = GraphBuilder()

    graph = builder.build(
        nodes=nodes,
        relationships=relationships
    )


    # Debug output
    print("\n=== FINAL GRAPH NODES ===")
    for node in graph.nodes:
        print(
            node.id,
            "|",
            node.type,
            "|",
            node.data.get("name")
        )


    # Assert no duplicate ENTITY
    entities = [
        n for n in graph.nodes
        if n.type == "ENTITY"
        and normalize(n.data.get("name"))
        == "muhammad"
    ]

    assert len(entities) == 0, (
        "Duplicate ENTITY Muhammad still exists"
    )


    # Ensure PERSON survived
    persons = [
        n for n in graph.nodes
        if n.type == "PERSON"
        and normalize(n.data.get("name"))
        == "muhammad"
    ]

    assert len(persons) == 1


    # Ensure relationship points to PERSON
    assert any(
        edge.source == "muhammad"
        and edge.target == "makkah"
        and edge.relation == "traveled_to"
        for edge in graph.edges
    )


def test_duplicate_cleanup_removes_entity_nodes():
    """
    Direct cleanup test.
    Simulates the bad state:
    PERSON Muhammad + ENTITY Muhammad
    """

    nodes = [
        KnowledgeNode(
            id="muhammad",
            type="PERSON",
            data={"name": "Muhammad"}
        ),

        KnowledgeNode(
            id="muhammad_entity",
            type="ENTITY",
            data={"name": "Muhammad"}
        ),

        KnowledgeNode(
            id="makkah",
            type="LOCATION",
            data={"name": "Makkah"}
        ),
    ]

    relationships = [
        KnowledgeRelationship(
            source="muhammad_entity",
            target="makkah",
            relation="traveled_to",
            metadata={}
        )
    ]

    builder = GraphBuilder()

    graph = builder.build(
        nodes=nodes,
        relationships=relationships
    )


    print("\n=== CLEANUP RESULT ===")
    for node in graph.nodes:
        print(
            node.id,
            "|",
            node.type,
            "|",
            node.data.get("name")
        )


    duplicate_entities = [
        n
        for n in graph.nodes
        if n.type == "ENTITY"
        and normalize(n.data.get("name"))
        == "muhammad"
    ]

    assert not duplicate_entities