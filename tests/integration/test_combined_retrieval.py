from src.application.retrieval.models import RetrievalRequest


def test_combined_retrieval_uses_logical_and(
    retrieval_runtime_engine,
    retrieval_index,
):
    fingerprint = next(iter(retrieval_index.fingerprint_index))
    request = RetrievalRequest(
        request_id="combined-retrieval",
        fingerprints=[fingerprint],
        media_types=["image/jpeg"],
        metadata_keys=["title"],
        metadata_values=["Example"],
    )
    result = retrieval_runtime_engine.execute_retrieval(request, retrieval_index)

    assert result.match_count == 1
    assert result.matches[0].record.fingerprint == fingerprint
