def test_validation_assignment_follows_acquisition_methods(
    source_ingestion_architect,
    source_acquisition_plan,
):
    expected = {
        "ARCHIVE_REQUEST": "STRICT",
        "CATALOG_LOOKUP": "STANDARD",
        "DOCUMENT_RETRIEVAL": "STRICT",
        "MAP_RETRIEVAL": "STANDARD",
        "ACADEMIC_LOOKUP": "STRICT",
        "COLLECTION_REVIEW": "BASIC",
        "INTERNAL_FETCH": "BASIC",
    }

    assert source_ingestion_architect.assign_validation_levels(
        source_acquisition_plan
    ) == {
        target.target_id: expected[target.acquisition_method]
        for batch in source_acquisition_plan.batches
        for target in batch.targets
    }
