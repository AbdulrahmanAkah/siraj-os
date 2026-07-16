def test_structure_validation_requires_complete_unique_valid_architecture(
    narrative_architect,
    documentary_plan,
):
    architecture = narrative_architect.build_narrative_architecture(documentary_plan)

    assert narrative_architect.validate_structure(architecture)
    architecture.beats.append(architecture.beats[0])
    assert not narrative_architect.validate_structure(architecture)


def test_script_structure_validation_requires_unique_complete_segments(
    script_architect,
    narrative_architecture,
):
    structure = script_architect.build_script_structure(narrative_architecture)

    assert script_architect.validate_structure(structure)
    structure.segments.append(structure.segments[0])
    assert not script_architect.validate_structure(structure)
