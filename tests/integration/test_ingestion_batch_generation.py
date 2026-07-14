def test_ingestion_batch_generation_has_one_batch_per_acquisition_batch(
    source_ingestion_architect,
    source_acquisition_plan,
):
    batches = source_ingestion_architect.generate_ingestion_batches(
        source_acquisition_plan
    )

    assert [batch.acquisition_batch_id for batch in batches] == [
        acquisition_batch.batch_id
        for acquisition_batch in source_acquisition_plan.batches
    ]
    assert all(batch.units for batch in batches)
