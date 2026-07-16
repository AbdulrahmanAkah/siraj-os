def test_chronological_sorting(
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
    dated = [entry.event_date for entry in entries if entry.event_date is not None]
    undated = [entry for entry in entries if entry.event_date is None]

    assert dated == sorted(dated)
    assert entries == sorted(
        entries,
        key=lambda entry: (
            entry.event_date is None,
            entry.event_date or "",
            entry.event_id,
        ),
    )
    if undated:
        assert all(entry.event_date is None for entry in entries[-len(undated):])
