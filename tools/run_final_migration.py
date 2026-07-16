from pathlib import Path

replacements = {
    "domain.claims.claim": "domain.knowledge_objects.claim",
    "domain.entities.entity": "domain.knowledge_objects.entity",
    "domain.entities": "domain.knowledge_objects",
    "domain.sources.source": "domain.knowledge_objects.source",
    "domain.sources": "domain.knowledge_objects",
    "domain.relationships.relationship": "domain.knowledge_objects.relationship",
    "domain.relationships": "domain.knowledge_objects",

    "application.documentary.documentary_outline": "application.models.outline",
    "application.models.llm.prompt": "application.models.prompt",
    "application.llm.core.llm_gateway": "application.ports.llm_gateway",

    "application.services.narrative_builder": "application.narrative.narrative_builder",
    "application.planning.scene_planner": "application.planning.scene_plan",
}

root = Path("src")

for file in root.rglob("*.py"):

    try:
        text = file.read_text(encoding="utf-8")
    except:
        continue

    original = text

    for old, new in replacements.items():
        text = text.replace(old, new)

    if text != original:
        file.write_text(
            text,
            encoding="utf-8"
        )
        print("Updated:", file)

print("Migration complete")
