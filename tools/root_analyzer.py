from pathlib import Path
import json

graph = json.loads(Path("dependency_graph.json").read_text(encoding="utf8"))

roots = []

for module, data in graph.items():

    if len(data["used_by"]) == 0:

        roots.append(module)

print("=" * 80)
print("ROOT MODULES")
print("=" * 80)

for r in sorted(roots):
    print(r)

print()
print("=" * 80)
print("COUNT:", len(roots))
print("=" * 80)