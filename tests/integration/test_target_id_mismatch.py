import pytest

from src.application.source_ingestion_runtime.models import IngestionPayload


def test_target_id_mismatch_is_rejected_deterministically(
    source_ingestion_executor,
    source_ingestion_plan,
    ingestion_payloads,
):
    target_id = next(iter(ingestion_payloads))
    payloads = dict(ingestion_payloads)
    payloads[target_id] = IngestionPayload(
        target_id="different-target",
        content_bytes=b"content",
        media_type="image/jpeg",
        metadata={},
    )

    assert not source_ingestion_executor.validate_runtime_inputs(
        source_ingestion_plan,
        payloads,
    )
    with pytest.raises(ValueError, match="Invalid ingestion runtime inputs"):
        source_ingestion_executor.execute_ingestion(source_ingestion_plan, payloads)
