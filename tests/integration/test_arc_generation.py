def test_narrative_architecture_builds_beginning_middle_and_end_arcs(
    narrative_architect,
    documentary_plan,
):
    architecture = narrative_architect.build_narrative_architecture(documentary_plan)

    assert [arc.title for arc in architecture.arcs] == ["Beginning", "Middle", "End"]
    assert all(arc.beat_ids for arc in architecture.arcs)
    assert len({arc.arc_id for arc in architecture.arcs}) == 3
