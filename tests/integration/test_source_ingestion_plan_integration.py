def test_source_ingestion_plan_integrates_into_runtime(
    source_ingestion_executor,
    source_ingestion_plan,
    ingestion_payloads,
):
    execution = source_ingestion_executor.execute_ingestion(
        source_ingestion_plan,
        ingestion_payloads,
    )

    assert execution.source_ingestion_plan_id == source_ingestion_plan.plan_id
    assert len(execution.validation_results) == execution.processed_count
    assert execution.execution_id.startswith("ingestion_execution_")
