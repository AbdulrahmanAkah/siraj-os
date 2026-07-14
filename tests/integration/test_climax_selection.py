def test_exactly_one_climax_is_assigned_to_the_highest_importance_section(
    narrative_architect,
    documentary_plan,
):
    architecture = narrative_architect.build_narrative_architecture(documentary_plan)
    climax_beats = [
        beat for beat in architecture.beats if beat.beat_type == "CLIMAX"
    ]

    assert len(climax_beats) == 1
    assert climax_beats[0].section_id == "chapter_2"
