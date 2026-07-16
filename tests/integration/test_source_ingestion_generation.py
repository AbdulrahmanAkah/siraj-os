def test_source_ingestion_plan_generates_ordered_batches(
    source_ingestion_architect,
    source_acquisition_plan,
):
    plan = source_ingestion_architect.build_source_ingestion_plan(
        source_acquisition_plan
    )

    assert plan.source_acquisition_plan_id == source_acquisition_plan.plan_id
    assert len(plan.batches) == len(source_acquisition_plan.batches)
    assert plan.unit_count == sum(
        len(batch.units) for batch in plan.batches
    )
    assert source_ingestion_architect.validate_ingestion_plan(
        plan,
        source_acquisition_plan,
    )


def test_source_ingestion_generation_is_deterministic(
    source_ingestion_architect,
    source_acquisition_plan,
):
    assert source_ingestion_architect.build_source_ingestion_plan(
        source_acquisition_plan
    ) == source_ingestion_architect.build_source_ingestion_plan(
        source_acquisition_plan
    )
