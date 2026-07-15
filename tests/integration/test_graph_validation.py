from dataclasses import replace


def test_relationship_graph_validation(
    relationship_graph_runtime,
    relationship_graph_plan,
    relationship_graph_inputs,
):
    result = relationship_graph_runtime.execute_relationship_graph(
        relationship_graph_plan,
        *relationship_graph_inputs,
    )
    invalid_graph = replace(result.graph, node_count=result.graph.node_count + 1)
    invalid_result = replace(result, graph=invalid_graph)

    assert relationship_graph_runtime.validate_graph(
        relationship_graph_plan,
        *relationship_graph_inputs,
        result,
    )
    assert not relationship_graph_runtime.validate_graph(
        relationship_graph_plan,
        *relationship_graph_inputs,
        invalid_result,
    )
