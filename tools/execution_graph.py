
import json
from pathlib import Path
from collections import defaultdict

REPORTS = Path("reports")

symbols_data = json.loads((REPORTS/"symbol_analysis.json").read_text(encoding="utf8"))
symbols = symbols_data["symbols"]

deps = json.loads((REPORTS/"dependency_graph_ast.json").read_text(encoding="utf8"))
reach = json.loads((REPORTS/"reachability.json").read_text(encoding="utf8"))

reachable = set(reach["reachable"])
roots = set(reach["roots"])

calls = defaultdict(set)
called_by = defaultdict(set)

for sym in symbols:
    module = sym["module"]

    for ref in sym.get("references", []):
        target = ref.get("module")
        if target:
            calls[module].add(target)
            called_by[target].add(module)

graph = {}

for module in deps:

    graph[module] = {
        "reachable": module in reachable,
        "root": module in roots,
        "imports": deps[module],
        "calls": sorted(calls[module]),
        "called_by": sorted(called_by[module]),
        "fan_out": len(calls[module]),
        "fan_in": len(called_by[module]),
    }

(REPORTS/"execution_graph.json").write_text(
    json.dumps(graph,indent=2,ensure_ascii=False),
    encoding="utf8"
)

print("="*70)
print("EXECUTION GRAPH GENERATED")
print("="*70)
print("Modules:",len(graph))
print("="*70)
