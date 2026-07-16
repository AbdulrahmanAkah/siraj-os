from src.application.repository_query.models import QueryRequest


def test_snapshot_querying_uses_snapshot_records(repository_query_engine):
    snapshot = repository_query_engine.knowledge_repository.build_snapshot()
    request = QueryRequest(
        query_id="snapshot-query",
        media_types=["image/jpeg"],
    )
    result = repository_query_engine.query_repository(request, snapshot)

    assert result.match_count == snapshot.record_count
    assert result.matched_records == snapshot.records
