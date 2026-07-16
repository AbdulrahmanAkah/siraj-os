def test_duplicate_edges_are_removed(
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
    edge_ids = [edge.edge_id for edge in edges]

    assert len(edge_ids) == len(set(edge_ids))
