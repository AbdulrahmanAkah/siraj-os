import json
import shutil
from pathlib import Path


ROOT = Path(".")
SRC = ROOT / "src"
ARCHIVE = ROOT / "archive" / "duplicates"
RULES = ROOT / "config" / "archive_rules.json"


def module_to_path(module):
    parts = module.split(".")
    
    if parts[0] == "src":
        parts = parts[1:]

    return SRC.joinpath(*parts).with_suffix(".py")


def archive_file(module):

    source = module_to_path(module)

    if not source.exists():
        print("SKIP:", module)
        return False

    relative = source.relative_to(SRC)

    target = ARCHIVE / relative

    target.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    shutil.move(
        str(source),
        str(target)
    )

    print(
        "Archived:",
        module,
        "->",
        target
    )

    return True


def main():

    rules = json.loads(
        RULES.read_text(
            encoding="utf-8"
        )
    )

    count = 0

    for module in rules["archive"]:
        if archive_file(module):
            count += 1

    print()
    print("=" * 60)
    print("Archived files:", count)
    print("=" * 60)


if __name__ == "__main__":
    main()