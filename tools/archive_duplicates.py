from pathlib import Path
import json
import shutil


ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
REPORT = ROOT / "reports" / "duplicate_symbols.json"
ARCHIVE = ROOT / "archive" / "duplicates"


CANONICAL = {
    "domain.claims.claim":
        "domain.knowledge_objects.claim",

    "domain.entities.entity":
        "domain.knowledge_objects.entity",

    "domain.sources.source":
        "domain.knowledge_objects.source",

    "domain.relationships.relationship":
        "domain.knowledge_objects.relationship",

    "application.models.llm.prompt":
        "application.models.prompt",

    "application.llm.core.llm_gateway":
        "application.ports.llm_gateway",

    "application.documentary.documentary_outline":
        "application.models.outline",

    "application.services.narrative_builder":
        "application.narrative.narrative_builder",
}


def module_to_file(module: str):
    parts = module.split(".")

    if parts[0] == "src":
        parts = parts[1:]

    return SRC.joinpath(*parts).with_suffix(".py")


def create_stub(target_module: str):
    return (
        f"from src.{target_module} import *\n\n"
        "__all__ = []\n"
    )


def archive_file(path: Path, module: str, target: str):

    relative = path.relative_to(SRC)

    destination = ARCHIVE / relative

    destination.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    shutil.move(
        str(path),
        str(destination)
    )

    path.write_text(
        create_stub(target),
        encoding="utf-8"
    )

    print(
        f"Archived: {module} -> {destination}"
    )


def main():

    if not REPORT.exists():
        print("Missing duplicate report")
        return


    data = json.loads(
        REPORT.read_text(
            encoding="utf-8"
        )
    )


    archived = 0


    for symbol, modules in data.items():

        canonical = None

        for m in modules:
            if m in CANONICAL.values():
                canonical = m
                break


        if not canonical:
            continue


        for module in modules:

            if module == canonical:
                continue


            file = module_to_file(module)

            if not file.exists():
                continue


            archive_file(
                file,
                module,
                canonical
            )

            archived += 1


    print()
    print("=" * 60)
    print(
        f"Archived files: {archived}"
    )
    print("=" * 60)



if __name__ == "__main__":
    main()