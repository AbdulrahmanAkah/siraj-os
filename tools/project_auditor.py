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
from project_auditor.architecture_index import build_architecture_index
from project_auditor.symbol_index import build_symbol_index
from project_auditor.import_fixes import build_import_fixes

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
    import_index = build_import_index(modules)
    missing = detect_missing_imports(modules)
    architecture = build_architecture_index(modules)
    symbols = build_symbol_index(modules)
    fixes = build_import_fixes(missing)
    graph = build_dependency_graph(modules)
    architecture = build_architecture_index(modules)
    symbols = build_symbol_index(modules)
    fixes = build_import_fixes(missing)

    write_report("statistics.json", stats)
    write_report("imports.json", import_index)
    write_report("dependency_graph.json", graph)
    write_report("missing_imports.json", missing)
    write_report("architecture_index.json", architecture)
    write_report("symbol_index.json", symbols)
    write_report("import_fixes.json", fixes)


    print("=" * 60)
    print("Project Statistics")
    print("=" * 60)

    for k, v in stats.items():
        print(f"{k:15} {v}")

    print()
    print("Dependency Graph :", len(graph)) # type: ignore
    print("Missing Imports  :", len(missing)) # type: ignore


if __name__ == "__main__":
    main()
