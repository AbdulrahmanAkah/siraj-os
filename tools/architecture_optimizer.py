
import json
from pathlib import Path

REPORTS = Path("reports")

intel = json.loads((REPORTS/"architecture_intelligence.json").read_text(encoding="utf8"))
clusters = json.loads((REPORTS/"module_clusters.json").read_text(encoding="utf8"))

cluster_lookup = {}
for k,v in clusters.items():
    for m in v:
        cluster_lookup[m]=k

result=[]

for item in intel:
    module=item["module"]
    item["cluster"]=cluster_lookup.get(module,"unknown")
    result.append(item)

(REPORTS/"architecture_optimizer.json").write_text(
    json.dumps(result,indent=2,ensure_ascii=False),
    encoding="utf8"
)

print("OPTIMIZER:",len(result))
