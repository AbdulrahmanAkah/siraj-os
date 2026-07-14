def test_segment_types_follow_the_canonical_beat_mapping(
    script_architect,
    narrative_architecture,
):
    types_by_beat_type = {
        beat.beat_type: script_architect.assign_segment_types(narrative_architecture)[
            beat.beat_id
        ]
        for beat in narrative_architecture.beats
    }

    assert types_by_beat_type == {
        "SETUP": "OPENING_HOOK",
        "CONTEXT": "BACKGROUND",
        "ESCALATION": "DEVELOPMENT",
        "TURNING_POINT": "REVEAL",
        "CLIMAX": "CLIMAX",
        "AFTERMATH": "RESOLUTION",
        "LEGACY": "EPILOGUE",
    }
