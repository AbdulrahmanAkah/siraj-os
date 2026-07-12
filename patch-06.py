from pathlib import Path
import textwrap

ROOT = Path(".")
AUDITOR = ROOT / "tools" / "project_auditor.py"
IMPORT_RESOLVER = ROOT / "tools" / "project_auditor" / "import_resolver.py"

AUDITOR.write_text(textwrap.dedent("""
from project_auditor.file_scanner import scan_python_files
from project_auditor.ast_parser import parse_module
from project_auditor.statistics import build_statistics
from project_auditor.report_writer import write_report
from project_auditor.import_resolver import (
    build_import_index,
    detect_missing_imports,
)
from project_auditor.dependency_graph import (
    build_dependency_graph,
)


def main():

    modules = {}

    for file in scan_python_files():

        module_name = (
            file.with_suffix("")
            .as_posix()
            .replace("/", ".")
        )

        modules[module_name] = parse_module(file)

    stats = build_statistics(modules)

    imports = build_import_index(modules)

    graph = build_dependency_graph(modules)

    missing = detect_missing_imports(modules)

    write_report("statistics.json", stats)
    write_report("imports.json", imports)
    write_report("dependency_graph.json", graph)
    write_report("missing_imports.json", missing)

    print("=" * 60)
    print("Project Statistics")
    print("=" * 60)

    for k, v in stats.items():
        print(f"{k:15} {v}")

    print()
    print("Dependency Graph :", len(graph))
    print("Missing Imports  :", len(missing))


if __name__ == "__main__":
    main()
""").strip() + "\n", encoding="utf8")


IMPORT_RESOLVER.write_text(textwrap.dedent("""
def normalize_import(module):

    if not module:
        return ""

    module = module.replace("\\\\", "/")
    module = module.replace("/", ".")

    if module.endswith(".py"):
        module = module[:-3]

    while ".." in module:
        module = module.replace("..", ".")

    return module.strip(".")


def build_import_index(modules):

    result = {}

    for module_name, info in modules.items():

        result[module_name] = sorted(
            normalize_import(i)
            for i in info.imports
            if normalize_import(i)
        )

    return result


def detect_missing_imports(modules):

    existing = set(modules.keys())

    missing = {}

    prefixes = (
        "application",
        "domain",
        "core",
        "infrastructure",
    )

    for module_name, info in modules.items():

        bad = []

        for imp in info.imports:

            imp = normalize_import(imp)

            if not imp:
                continue

            if imp.startswith(prefixes):
                imp = "src." + imp

            if imp.startswith("src.") and imp not in existing:
                bad.append(imp)

        if bad:
            missing[module_name] = sorted(set(bad))

    return missing
""").strip() + "\n", encoding="utf8")


print("Patch-06 applied successfully.")