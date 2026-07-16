def test_fingerprint_assignment_follows_acquisition_methods(
    source_ingestion_architect,
    source_acquisition_plan,
):
    expected = {
        "ARCHIVE_REQUEST": "SHA256_FINGERPRINT",
        "CATALOG_LOOKUP": "METADATA_FINGERPRINT",
        "DOCUMENT_RETRIEVAL": "SHA256_FINGERPRINT",
        "MAP_RETRIEVAL": "PERCEPTUAL_FINGERPRINT",
        "ACADEMIC_LOOKUP": "SHA256_FINGERPRINT",
        "COLLECTION_REVIEW": "PERCEPTUAL_FINGERPRINT",
        "INTERNAL_FETCH": "METADATA_FINGERPRINT",
    }

    assert source_ingestion_architect.assign_fingerprint_strategies(
        source_acquisition_plan
    ) == {
        target.target_id: expected[target.acquisition_method]
        for batch in source_acquisition_plan.batches
        for target in batch.targets
    }
