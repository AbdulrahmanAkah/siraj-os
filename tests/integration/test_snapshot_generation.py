def test_snapshot_generation_and_export_are_deterministic(
    knowledge_repository,
    repository_ingestion_result,
):
    knowledge_repository.load_repository_documents(
        repository_ingestion_result.created_documents
    )
    snapshot = knowledge_repository.build_snapshot()
    exported = knowledge_repository.export_repository_snapshot()

    assert exported == snapshot
    assert snapshot.snapshot_id.startswith("repository_snapshot_")
    assert snapshot.record_count == len(snapshot.records)
