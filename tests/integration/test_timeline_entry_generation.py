def test_timeline_entry_generation(
    historical_timeline_runtime,
    historical_timeline_plan,
    historical_timeline_inputs,
):
    event_result, graph_result = historical_timeline_inputs
    candidates = historical_timeline_runtime.create_timeline_candidates(
        historical_timeline_plan,
        event_result,
        graph_result,
    )
    entries = historical_timeline_runtime.create_timeline_entries(candidates)

    assert entries
    assert len(entries) == len({entry.event_id for entry in entries})
    assert all(entry.entry_id.startswith("timeline_entry_") for entry in entries)
    assert all(entry.event_id for entry in entries)
