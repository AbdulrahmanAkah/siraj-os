def test_source_acquisition_plan_integrates_into_ingestion_plan(
    source_ingestion_architect,
    source_acquisition_plan,
):
    plan = source_ingestion_architect.build_source_ingestion_plan(
        source_acquisition_plan
    )

    assert plan.source_acquisition_plan_id == source_acquisition_plan.plan_id
    assert source_ingestion_architect.validate_ingestion_plan(plan)
