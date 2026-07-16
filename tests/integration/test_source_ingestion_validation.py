def test_source_ingestion_validation_rejects_orphan_units(
    source_ingestion_architect,
    source_acquisition_plan,
):
    plan = source_ingestion_architect.build_source_ingestion_plan(
        source_acquisition_plan
    )

    assert source_ingestion_architect.validate_ingestion_plan(
        plan,
        source_acquisition_plan,
    )
    plan.batches[0].units[0].acquisition_target_id = "orphan_target"
    assert not source_ingestion_architect.validate_ingestion_plan(
        plan,
        source_acquisition_plan,
    )
