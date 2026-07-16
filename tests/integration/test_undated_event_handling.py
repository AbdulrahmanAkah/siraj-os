def test_undated_event_handling(
    historical_timeline_runtime,
    historical_timeline_plan,
    historical_timeline_inputs,
):
    event_result, graph_result = historical_timeline_inputs
    result = historical_timeline_runtime.build_timeline(
        historical_timeline_plan,
        event_result,
        graph_result,
    )
    entries = result.timeline.entries
    undated = [entry for entry in entries if entry.event_date is None]

    assert undated
    assert all(entry.event_date is None for entry in entries[-len(undated):])
    assert [entry.event_id for entry in undated] == sorted(
        entry.event_id for entry in undated
    )
