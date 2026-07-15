from dataclasses import replace


def test_duplicate_event_handling(
    historical_timeline_runtime,
    historical_timeline_plan,
    historical_timeline_inputs,
):
    event_result, graph_result = historical_timeline_inputs
    duplicated = replace(
        event_result,
        events=event_result.events + [event_result.events[0]],
        event_count=event_result.event_count + 1,
    )

    result = historical_timeline_runtime.build_timeline(
        historical_timeline_plan,
        duplicated,
        graph_result,
    )

    assert result.timeline.entry_count == len(event_result.events)
    assert len({entry.event_id for entry in result.timeline.entries}) == result.timeline.entry_count
