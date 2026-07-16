import json
from pathlib import Path


PATTERNS = {
    "domain.entities": "domain.knowledge_objects",
    "domain.claims": "domain.knowledge_objects.claim",
    "domain.sources": "domain.knowledge_objects.source",
    "application.models.llm.prompt": "application.models.prompt",
    "application.services.narrative_builder": "application.narrative.narrative_builder",
    "core.storage.json_storage": "infrastructure.storage.json_storage",
    "core.repositories.entity_repository": "domain.repositories.entity_repository",
}


results = {}


for file in Path("src").rglob("*.py"):

    try:
        text = file.read_text(
            encoding="utf8",
            errors="ignore"
        )
    except:
        continue

    matches = []

    for old, new in PATTERNS.items():

        if old in text:

            matches.append({
                "old": old,
                "target": new
            })


    if matches:

        results[str(file)] = matches



Path("reports/deep_import_migration_preview.json").write_text(
    json.dumps(
        results,
        indent=4,
        ensure_ascii=False
    ),
    encoding="utf8"
)


print("=" * 60)
print("DEEP IMPORT MIGRATION PREVIEW")
print("=" * 60)
print("Files affected:", len(results))
print("Saved: reports/deep_import_migration_preview.json")
