from pathlib import Path
import json
from graphlib import TopologicalSorter, CycleError

graph_file = Path("reports/dependency_graph.json")
out_file = Path("reports/cycles.json")

graph = json.loads(
    graph_file.read_text(encoding="utf8")
)

try:
    list(TopologicalSorter(graph).static_order())
    cycles = []

except CycleError as e:
    cycles = list(e.args)

out_file.write_text(
    json.dumps(
        cycles,
        indent=4,
        ensure_ascii=False
    ),
    encoding="utf8"
)

print("Cycles:", len(cycles))
print("Saved:", out_file)
