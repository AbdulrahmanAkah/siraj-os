from dataclasses import replace

from src.application.retrieval.models import RetrievalRequest


def test_retrieval_request_and_index_validation(
    retrieval_runtime_engine,
    retrieval_index,
):
    valid_request = RetrievalRequest(request_id="valid")
    invalid_request = RetrievalRequest(
        request_id="invalid",
        metadata_keys=["title", "title"],
    )

    assert retrieval_runtime_engine.validate_retrieval_request(valid_request)
    assert not retrieval_runtime_engine.validate_retrieval_request(invalid_request)
    assert retrieval_runtime_engine.validate_retrieval_index(retrieval_index)
    assert not retrieval_runtime_engine.validate_retrieval_index(
        replace(retrieval_index, index_id="invalid")
    )
