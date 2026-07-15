from dataclasses import replace


def test_repository_validation_and_snapshot_consistency(
    knowledge_repository,
    repository_ingestion_result,
):
    knowledge_repository.load_repository_documents(
        repository_ingestion_result.created_documents
    )
    snapshot = knowledge_repository.build_snapshot()

    assert knowledge_repository.validate_repository()
    assert knowledge_repository.validate_repository(snapshot)
    assert not knowledge_repository.validate_repository(
        replace(snapshot, record_count=snapshot.record_count + 1)
    )
