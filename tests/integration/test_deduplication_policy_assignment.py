def test_deduplication_assignment_follows_acquisition_methods(
    source_ingestion_architect,
    source_acquisition_plan,
):
    expected = {
        "ARCHIVE_REQUEST": "STRICT_DEDUPLICATION",
        "CATALOG_LOOKUP": "STANDARD_DEDUPLICATION",
        "DOCUMENT_RETRIEVAL": "STRICT_DEDUPLICATION",
        "MAP_RETRIEVAL": "STANDARD_DEDUPLICATION",
        "ACADEMIC_LOOKUP": "STRICT_DEDUPLICATION",
        "COLLECTION_REVIEW": "RELAXED_DEDUPLICATION",
        "INTERNAL_FETCH": "STANDARD_DEDUPLICATION",
    }

    assert source_ingestion_architect.assign_deduplication_policies(
        source_acquisition_plan
    ) == {
        target.target_id: expected[target.acquisition_method]
        for batch in source_acquisition_plan.batches
        for target in batch.targets
    }
