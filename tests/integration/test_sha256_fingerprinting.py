from hashlib import sha256


def test_sha256_fingerprint_hashes_normalized_bytes(
    source_ingestion_executor,
    source_ingestion_plan,
    ingestion_payloads,
):
    result = source_ingestion_executor.execute_ingestion(
        source_ingestion_plan,
        ingestion_payloads,
    )
    units = {
        unit.unit_id: unit
        for batch in source_ingestion_plan.batches
        for unit in batch.units
    }
    normalized = next(
        payload
        for payload in result.normalized_payloads
        if units[payload.unit_id].fingerprint_strategy == "SHA256_FINGERPRINT"
    )
    fingerprint = next(
        item for item in result.fingerprints if item.unit_id == normalized.unit_id
    )

    assert fingerprint.fingerprint == sha256(normalized.normalized_bytes).hexdigest()
