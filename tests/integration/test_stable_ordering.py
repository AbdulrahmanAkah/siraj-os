from dataclasses import replace


def test_script_segments_follow_beat_position_then_stable_beat_id(
    script_architect,
    narrative_architecture,
):
    reordered_architecture = replace(
        narrative_architecture,
        beats=list(reversed(narrative_architecture.beats)),
    )

    segments = script_architect.generate_segments(reordered_architecture)
    expected_beats = sorted(
        reordered_architecture.beats,
        key=lambda beat: (beat.position, beat.beat_id),
    )

    assert [segment.beat_id for segment in segments] == [
        beat.beat_id for beat in expected_beats
    ]
