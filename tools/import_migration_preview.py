import json
from pathlib import Path


MIGRATIONS = {

    "domain.entities.entity.Person":
        "domain.knowledge_objects.person.Person",

    "domain.knowledge_objects.person.Person":
        "domain.knowledge_objects.person.Person",

    "domain.claims.claim.Claim":
        "domain.knowledge_objects.claim.Claim",

    "domain.knowledge_objects.claim.Claim":
        "domain.knowledge_objects.claim.Claim",

    "domain.knowledge_objects.event.Event":
        "domain.knowledge_objects.event.Event",

    "domain.sources.source.Source":
        "domain.knowledge_objects.source.Source",

    "application.models.llm.prompt.Prompt":
        "application.models.prompt.Prompt",

    "application.ports.llm_gateway.LLMGateway":
        "application.ports.llm_gateway.LLMGateway",
}


def scan():

    results = {}

    for file in Path("src").rglob("*.py"):

        text = file.read_text(
            encoding="utf8",
            errors="ignore"
        )

        found = []

        for old, new in MIGRATIONS.items():

            if old in text:

                found.append({
                    "old": old,
                    "new": new
                })

        if found:

            results[str(file)] = found

    return results



report = scan()

Path("reports/import_migration_preview.json").write_text(
    json.dumps(
        report,
        indent=4,
        ensure_ascii=False
    ),
    encoding="utf8"
)

print("=" * 60)
print("IMPORT MIGRATION PREVIEW")
print("=" * 60)
print("Files affected:", len(report))
print("Saved: reports/import_migration_preview.json")
