def test_snapshot_records_are_ordered_by_record_id(
    knowledge_repository,
    repository_ingestion_result,
):
    knowledge_repository.load_repository_documents(
        list(reversed(repository_ingestion_result.created_documents))
    )
    snapshot = knowledge_repository.build_snapshot()

    assert [record.record_id for record in snapshot.records] == sorted(
        record.record_id for record in snapshot.records
    )
