from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"

graph = json.loads(
    (REPORTS/"dependency_graph_ast.json").read_text(encoding="utf8")
)

modules = set(graph.keys())

roots = []

for m in modules:

    if (
        m == "main"
        or m.startswith("cli.")
        or m.startswith("application.workflow")
    ):
        roots.append(m)

visited = set()

stack = roots[:]

while stack:

    node = stack.pop()

    if node in visited:
        continue

    visited.add(node)

    for dep in graph.get(node, []):

        if dep in modules and dep not in visited:
            stack.append(dep)

reachable = sorted(visited)

unreachable = sorted(modules - visited)

reverse = {m: [] for m in modules}

for src, deps in graph.items():

    for d in deps:

        if d in reverse:
            reverse[d].append(src)

orphans = sorted([
    m for m in unreachable
    if len(reverse[m]) == 0
])

(REPORTS/"reachable_modules.json").write_text(
    json.dumps(reachable,indent=2,ensure_ascii=False),
    encoding="utf8"
)

(REPORTS/"unreachable_modules.json").write_text(
    json.dumps(unreachable,indent=2,ensure_ascii=False),
    encoding="utf8"
)

(REPORTS/"reverse_dependency_graph.json").write_text(
    json.dumps(reverse,indent=2,ensure_ascii=False),
    encoding="utf8"
)

(REPORTS/"orphan_modules.json").write_text(
    json.dumps(orphans,indent=2,ensure_ascii=False),
    encoding="utf8"
)



import json
from pathlib import Path

REPORTS = Path(__file__).resolve().parents[1] / "reports"

(REPORTS/"reachability.json").write_text(
    json.dumps(
        {
            "roots": sorted(list(roots)),
            "reachable": sorted(list(reachable)),
            "unreachable": sorted(list(unreachable)),
            "orphans": sorted(list(orphans))
        },
        indent=2,
        ensure_ascii=False
    ),
    encoding="utf8"
)


print("="*70)
print("REACHABILITY ENGINE COMPLETE")
print("="*70)
print("Roots               :", len(roots))
print("Reachable modules   :", len(reachable))
print("Unreachable modules :", len(unreachable))
print("Orphan modules      :", len(orphans))
print("="*70)
