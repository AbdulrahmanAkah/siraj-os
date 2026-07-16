def test_script_structure_has_exactly_one_opening_hook_and_climax(
    script_architect,
    narrative_architecture,
):
    structure = script_architect.build_script_structure(narrative_architecture)
    segment_types = [segment.segment_type for segment in structure.segments]

    assert segment_types.count("OPENING_HOOK") == 1
    assert segment_types.count("CLIMAX") == 1
