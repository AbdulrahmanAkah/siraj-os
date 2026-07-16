from src.application.repository_query.models import QueryRequest


def test_query_validation_accepts_canonical_request(repository_query_engine):
    request = QueryRequest(
        query_id="query-valid",
        media_types=["image/jpeg"],
        metadata_filters={"title": "Example"},
    )

    assert repository_query_engine.validate_query(request)


def test_query_validation_rejects_duplicate_filter_values(repository_query_engine):
    request = QueryRequest(
        query_id="query-invalid",
        fingerprints=["same", "same"],
    )

    assert not repository_query_engine.validate_query(request)
