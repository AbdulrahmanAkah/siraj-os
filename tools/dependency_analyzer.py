from pathlib import Path
import ast
import json

ROOT = Path("src")

modules = {}
dependencies = {}

for file in ROOT.rglob("*.py"):
    module = ".".join(file.with_suffix("").parts)
    modules[module] = str(file)

for file in ROOT.rglob("*.py"):

    module = ".".join(file.with_suffix("").parts)

    deps = set()

    try:
        tree = ast.parse(file.read_text(encoding="utf8"))
    except Exception:
        continue

    for node in ast.walk(tree):

        if isinstance(node, ast.Import):
            for n in node.names:
                deps.add(n.name)

        elif isinstance(node, ast.ImportFrom):

            if node.module:
                deps.add(node.module)

    dependencies[module] = sorted(deps)

reverse = {}

for module in dependencies:

    reverse[module] = []

for module, deps in dependencies.items():

    for dep in deps:

        for candidate in modules:

            if dep == candidate:

                reverse.setdefault(candidate, []).append(module)

result = {}

for module in sorted(modules):

    result[module] = {
        "file": modules[module],
        "depends_on": dependencies.get(module, []),
        "used_by": sorted(reverse.get(module, [])),
    }

Path("dependency_graph.json").write_text(
    json.dumps(result, indent=2, ensure_ascii=False),
    encoding="utf8",
)

print("=" * 80)
print("DEPENDENCY GRAPH CREATED")
print("=" * 80)
print("Modules :", len(result))
print("Output  : dependency_graph.json")