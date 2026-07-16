from pathlib import Path
import json
import shutil


ROOT = Path(".")
REPORT = Path("reports/duplicate_symbols.json")
ARCHIVE = Path("archive/duplicates")


CANONICAL = {
    "Claim": "domain.knowledge_objects.claim",
    "Person": "domain.knowledge_objects.person",
    "Event": "domain.knowledge_objects.event",
    "Relationship": "domain.knowledge_objects.relationship",
    "Source": "domain.knowledge_objects.source",
    "TimelineEvent": "domain.knowledge_objects.timeline_event",
    "DocumentaryOutline": "application.models.outline",
    "Prompt": "application.models.prompt",
    "LLMGateway": "application.ports.llm_gateway",
    "NarrativeBuilder": "application.narrative.narrative_builder",
    "ScenePlan": "application.planning.scene_plan",
}


def module_to_path(module):

    return ROOT / "src" / Path(
        module.replace(".", "/")
    ).with_suffix(".py")


def archive_file(module):

    src = module_to_path(module)

    if not src.exists():
        return False

    target = ARCHIVE / Path(
        module.replace(".", "/")
    ).with_suffix(".py")

    target.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    shutil.move(
        src,
        target
    )

    print(
        f"Archived: {module} -> {target}"
    )

    return True


def main():

    data=json.loads(
        REPORT.read_text(
            encoding="utf-8"
        )
    )

    count=0

    for symbol, modules in data.items():

        keep=CANONICAL.get(symbol)

        if not keep:
            continue

        for module in modules:

            if module != keep:

                if archive_file(module):
                    count+=1


    print()
    print("="*60)
    print(
        f"Archived files: {count}"
    )
    print("="*60)


if __name__=="__main__":
    main()
