def test_resolution_plan_generation(evidence_resolution_architect):
    plan = evidence_resolution_architect.build_resolution_plan(
        allowed_source_types=["CLAIM", "EVENT"],
        validation_level="STRICT",
    )

    assert plan.plan_id.startswith("evidence_resolution_plan_")
    assert plan.allowed_source_types == ["CLAIM", "EVENT"]
    assert plan.validation_level == "STRICT"
    assert evidence_resolution_architect.validate_plan(plan)
