
import json
from pathlib import Path
from collections import defaultdict

REPORTS = Path("reports")

graph = json.loads((REPORTS/"execution_graph.json").read_text(encoding="utf8"))

clusters = defaultdict(list)

for module in graph:

    parts = module.split(".")

    if len(parts)>=2:
        key=".".join(parts[:2])
    else:
        key=parts[0]

    clusters[key].append(module)

clusters=dict(sorted(clusters.items()))

(REPORTS/"module_clusters.json").write_text(
    json.dumps(clusters,indent=2,ensure_ascii=False),
    encoding="utf8"
)

print("CLUSTERS:",len(clusters))
