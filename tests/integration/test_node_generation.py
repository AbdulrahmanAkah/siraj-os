def test_graph_node_generation(
    relationship_graph_runtime,
    relationship_graph_plan,
    relationship_graph_inputs,
):
    claims, entities, events = relationship_graph_inputs
    nodes = relationship_graph_runtime.generate_nodes(claims, entities, events)

    assert len(nodes) == len(claims.claims) + len(entities.entities) + len(events.events)
    assert {node.node_type for node in nodes} == {
        "CLAIM_NODE",
        "ENTITY_NODE",
        "EVENT_NODE",
    }
    assert [node.node_id for node in nodes] == sorted(node.node_id for node in nodes)
