def test_normalization_assignment_follows_acquisition_methods(
    source_ingestion_architect,
    source_acquisition_plan,
):
    expected = {
        "ARCHIVE_REQUEST": "ARCHIVE_NORMALIZATION",
        "CATALOG_LOOKUP": "METADATA_NORMALIZATION",
        "DOCUMENT_RETRIEVAL": "DOCUMENT_NORMALIZATION",
        "MAP_RETRIEVAL": "MAP_NORMALIZATION",
        "ACADEMIC_LOOKUP": "DOCUMENT_NORMALIZATION",
        "COLLECTION_REVIEW": "IMAGE_NORMALIZATION",
        "INTERNAL_FETCH": "METADATA_NORMALIZATION",
    }

    assert source_ingestion_architect.assign_normalization_strategies(
        source_acquisition_plan
    ) == {
        target.target_id: expected[target.acquisition_method]
        for batch in source_acquisition_plan.batches
        for target in batch.targets
    }
