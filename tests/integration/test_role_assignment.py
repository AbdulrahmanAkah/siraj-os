def test_narration_roles_follow_the_canonical_segment_mapping(
    narration_planner,
    script_structure,
):
    roles_by_segment_type = {
        segment.segment_type: narration_planner.assign_roles(script_structure)[
            segment.segment_id
        ]
        for segment in script_structure.segments
    }

    assert roles_by_segment_type == {
        "OPENING_HOOK": "HOOK",
        "BACKGROUND": "CONTEXT",
        "DEVELOPMENT": "EXPLANATION",
        "REVEAL": "REVELATION",
        "CLIMAX": "CLIMAX_NARRATION",
        "RESOLUTION": "RESOLUTION",
        "EPILOGUE": "LEGACY_REFLECTION",
    }
