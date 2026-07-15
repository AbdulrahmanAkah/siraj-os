def test_timeline_id_determinism(
    historical_timeline_runtime,
    historical_timeline_plan,
    historical_timeline_inputs,
):
    event_result, graph_result = historical_timeline_inputs
    first = historical_timeline_runtime.build_timeline(
        historical_timeline_plan,
        event_result,
        graph_result,
    )
    second = historical_timeline_runtime.build_timeline(
        historical_timeline_plan,
        event_result,
        graph_result,
    )

    assert first.timeline.timeline_id == second.timeline.timeline_id
    assert [entry.entry_id for entry in first.timeline.entries] == [
        entry.entry_id for entry in second.timeline.entries
    ]
