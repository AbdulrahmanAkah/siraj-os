def test_script_architect_generates_one_ordered_segment_per_beat(
    script_architect,
    narrative_architecture,
):
    segments = script_architect.generate_segments(narrative_architecture)

    assert len(segments) == len(narrative_architecture.beats)
    assert [segment.position for segment in segments] == list(range(len(segments)))
    assert {segment.beat_id for segment in segments} == {
        beat.beat_id for beat in narrative_architecture.beats
    }
