import json
from hashlib import sha256


def test_metadata_fingerprint_uses_sorted_stable_serialization(
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
        if units[payload.unit_id].fingerprint_strategy == "METADATA_FINGERPRINT"
    )
    fingerprint = next(
        item for item in result.fingerprints if item.unit_id == normalized.unit_id
    )
    serialized = json.dumps(
        normalized.normalized_metadata,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    assert fingerprint.fingerprint == sha256(serialized).hexdigest()
