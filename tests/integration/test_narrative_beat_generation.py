def test_narrative_architect_generates_ordered_beats(narrative_architect, documentary_plan):
    beats = narrative_architect.generate_beats(documentary_plan)

    assert [beat.position for beat in beats] == list(range(len(beats)))
    assert beats[0].beat_type == "SETUP"
    assert beats[1].beat_type == "CONTEXT"
    assert {event_id for beat in beats for event_id in beat.event_ids} == set(
        documentary_plan.selected_event_ids
    )
