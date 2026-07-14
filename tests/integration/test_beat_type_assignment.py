def test_beat_types_follow_canonical_section_rules(narrative_architect, documentary_plan):
    assignments = narrative_architect.assign_beat_types(documentary_plan)

    assert assignments["introduction"] == ["SETUP", "CONTEXT"]
    assert assignments["chapter_1"] == ["ESCALATION"]
    assert assignments["chapter_2"] == ["CLIMAX"]
    assert assignments["chapter_3"] == ["TURNING_POINT"]
    assert assignments["conclusion"] == ["AFTERMATH", "LEGACY"]
