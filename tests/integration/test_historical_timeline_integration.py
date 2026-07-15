def test_historical_timeline_integration(
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

    assert result.timeline.plan_id == historical_timeline_plan.plan_id
    assert result.timeline.entries
    assert all(
        entry.event_id in {event.event_id for event in event_result.events}
        for entry in result.timeline.entries
    )
