import json
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"

data = json.loads((REPORTS/"project_index.json").read_text(encoding="utf8"))

# ============================================================
# Duplicate Modules
# ============================================================

dup_classes = defaultdict(list)

for f in data:
    for c in f["classes"]:
        dup_classes[c].append(f["module"])

dup_classes = {k:v for k,v in dup_classes.items() if len(v)>1}

(REPORTS/"duplicate_symbols.json").write_text(
    json.dumps(dup_classes,indent=2,ensure_ascii=False),
    encoding="utf8"
)

# ============================================================
# Dataclasses
# ============================================================

dataclasses=[]

for f in data:
    for d in f["dataclasses"]:
        dataclasses.append({
            "module":f["module"],
            "class":d
        })

(REPORTS/"dataclasses.json").write_text(
    json.dumps(dataclasses,indent=2,ensure_ascii=False),
    encoding="utf8"
)

# ============================================================
# Enums
# ============================================================

enums=[]

for f in data:
    for e in f["enums"]:
        enums.append({
            "module":f["module"],
            "enum":e
        })

(REPORTS/"enums.json").write_text(
    json.dumps(enums,indent=2,ensure_ascii=False),
    encoding="utf8"
)

# ============================================================
# Dependency Graph
# ============================================================

graph={}

modules={x["module"] for x in data}

for f in data:

    deps=[]

    for imp in f["imports"]:

        for m in modules:

            if imp.startswith(m):
                deps.append(m)

    graph[f["module"]]=sorted(set(deps))

(REPORTS/"dependency_graph.json").write_text(
    json.dumps(graph,indent=2,ensure_ascii=False),
    encoding="utf8"
)

print("="*70)
print("Architecture Reports Generated")
print("="*70)
print("Duplicate classes :",len(dup_classes))
print("Dataclasses       :",len(dataclasses))
print("Enums             :",len(enums))
print("Modules           :",len(graph))
print("="*70)
