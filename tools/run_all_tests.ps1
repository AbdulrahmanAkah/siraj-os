Write-Host ""
Write-Host "==============================="
Write-Host " Running SIRAJ Test Suite"
Write-Host "==============================="
Write-Host ""

python src/test_timeline_extractor.py
python src/test_relationship_extractor.py
python src/test_character_extractor.py
python src/test_statistic_extractor.py
python src/test_knowledge_object_registry.py
python src/test_registry_queries.py
python src/test_knowledge_extraction_framework.py
python src/test_generation_pipeline.py

Write-Host ""
Write-Host "==============================="
Write-Host " Finished"
Write-Host "==============================="
