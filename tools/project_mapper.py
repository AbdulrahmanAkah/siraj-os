from pathlib import Path
import ast
import json

ROOT = Path("src")

result = {}

for file in ROOT.rglob("*.py"):
    try:
        source = file.read_text(encoding="utf8")
        tree = ast.parse(source)
    except Exception as e:
        result[str(file)] = {
            "error": str(e)
        }
        continue

    imports = []
    classes = []
    functions = []

    for node in ast.walk(tree):

        if isinstance(node, ast.Import):
            for n in node.names:
                imports.append(n.name)

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for n in node.names:
                imports.append(f"{module}.{n.name}")

        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)

        elif isinstance(node, ast.FunctionDef):
            functions.append(node.name)

    result[str(file)] = {
        "imports": sorted(set(imports)),
        "classes": classes,
        "functions": functions,
    }

Path("project_map.json").write_text(
    json.dumps(result, indent=2, ensure_ascii=False),
    encoding="utf8"
)

print()
print("=" * 80)
print("PROJECT MAP CREATED")
print("=" * 80)
print("Output : project_map.json")
print(f"Files  : {len(result)}")