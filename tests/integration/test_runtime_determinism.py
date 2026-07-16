def test_runtime_execution_is_deterministic(
    source_ingestion_executor,
    source_ingestion_plan,
    ingestion_payloads,
):
    first = source_ingestion_executor.execute_ingestion(
        source_ingestion_plan,
        ingestion_payloads,
    )
    second = source_ingestion_executor.execute_ingestion(
        source_ingestion_plan,
        dict(reversed(list(ingestion_payloads.items()))),
    )

    assert first == second
