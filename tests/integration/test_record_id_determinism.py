def test_record_ids_are_deterministic(
    knowledge_repository,
    repository_ingestion_result,
):
    documents = repository_ingestion_result.created_documents
    first = knowledge_repository.load_repository_documents(documents)
    second_repository = type(knowledge_repository)(
        knowledge_repository.repository_ingestion_engine
    )
    second = second_repository.load_repository_documents(
        list(reversed(documents))
    )

    assert sorted(record.record_id for record in first.created_records) == sorted(
        record.record_id for record in second.created_records
    )
