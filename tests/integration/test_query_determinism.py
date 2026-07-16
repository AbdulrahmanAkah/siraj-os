from src.application.repository_query.models import QueryRequest


def test_query_results_are_deterministic(repository_query_engine):
    request = QueryRequest(
        query_id="query-deterministic",
        media_types=["image/jpeg"],
    )
    first = repository_query_engine.query_repository(request)
    second = repository_query_engine.query_repository(request)

    assert first == second
    assert first.result_id == second.result_id
    assert [record.record_id for record in first.matched_records] == sorted(
        record.record_id for record in first.matched_records
    )
