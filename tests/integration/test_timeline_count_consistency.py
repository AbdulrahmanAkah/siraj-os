def test_timeline_count_consistency(
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

    assert result.timeline.entry_count == len(result.timeline.entries)
    assert result.entry_count == result.timeline.entry_count
