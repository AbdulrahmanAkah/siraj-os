from dataclasses import replace


def test_timeline_validation(
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
    invalid_timeline = replace(
        result.timeline,
        entry_count=result.timeline.entry_count + 1,
    )
    invalid_result = replace(result, timeline=invalid_timeline)

    assert historical_timeline_runtime.validate_timeline(
        historical_timeline_plan,
        event_result,
        graph_result,
        result,
    )
    assert not historical_timeline_runtime.validate_timeline(
        historical_timeline_plan,
        event_result,
        graph_result,
        invalid_result,
    )
