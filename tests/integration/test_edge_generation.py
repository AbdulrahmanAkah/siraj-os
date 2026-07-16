def test_graph_edge_generation(
    relationship_graph_runtime,
    relationship_graph_inputs,
):
    claims, entities, events = relationship_graph_inputs
    nodes = relationship_graph_runtime.generate_nodes(claims, entities, events)
    candidates = relationship_graph_runtime.generate_relationship_candidates(
        claims,
        entities,
        events,
        nodes,
    )
    edges = relationship_graph_runtime.generate_edges(candidates)

    assert edges
    assert {edge.edge_type for edge in edges} == {
        "REFERENCES",
        "SUPPORTED_BY",
        "ASSOCIATED_WITH",
        "LOCATED_IN",
        "OCCURRED_ON",
    }
