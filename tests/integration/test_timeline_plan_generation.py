def test_timeline_plan_generation(historical_timeline_architect):
    plan = historical_timeline_architect.build_timeline_plan(
        allowed_event_types=["PUBLICATION_EVENT", "DATE_EVENT"],
        include_undated_events=False,
        validation_level="STRICT",
    )

    assert plan.plan_id.startswith("historical_timeline_plan_")
    assert plan.allowed_event_types == ["PUBLICATION_EVENT", "DATE_EVENT"]
    assert plan.include_undated_events is False
    assert plan.validation_level == "STRICT"
    assert historical_timeline_architect.validate_plan(plan)
