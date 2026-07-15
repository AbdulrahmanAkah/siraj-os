from hashlib import sha256


def test_perceptual_fingerprint_is_documented_deterministic_placeholder(
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
        if units[payload.unit_id].fingerprint_strategy == "PERCEPTUAL_FINGERPRINT"
    )
    fingerprint = next(
        item for item in result.fingerprints if item.unit_id == normalized.unit_id
    )
    expected = sha256(
        normalized.normalized_media_type.encode("utf-8")
        + b"\x00"
        + normalized.normalized_bytes
    ).hexdigest()

    assert fingerprint.fingerprint == expected
