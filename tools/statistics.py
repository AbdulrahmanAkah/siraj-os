import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"

index = json.loads((REPORTS/"project_index.json").read_text(encoding="utf8"))
deps = json.loads((REPORTS/"dependency_graph_ast.json").read_text(encoding="utf8"))
reverse = json.loads((REPORTS/"reverse_dependency_graph.json").read_text(encoding="utf8"))
dead = set(json.loads((REPORTS/"dead_candidates.json").read_text(encoding="utf8")))
duplicates = json.loads((REPORTS/"duplicate_symbols.json").read_text(encoding="utf8"))

duplicate_lookup = {}

for cls, mods in duplicates.items():
    for m in mods:
        duplicate_lookup.setdefault(m, []).append(cls)

master=[]

for file in index:

    module=file["module"]

    incoming=len(reverse.get(module,[]))
    outgoing=len(deps.get(module,[]))

    risk=0

    if incoming>0:
        risk+=5

    if outgoing>10:
        risk+=2

    if module in dead:
        risk-=4

    if module=="main":
        risk+=100

    if module.startswith("cli"):
        risk+=50

    if module.startswith("test_"):
        risk-=5

    master.append({
        "module":module,
        "path":file["path"],
        "dead_candidate":module in dead,
        "incoming":incoming,
        "outgoing":outgoing,
        "classes":len(file["classes"]),
        "functions":len(file["functions"]),
        "duplicates":duplicate_lookup.get(module,[]),
        "risk_score":risk
    })

master.sort(key=lambda x:x["risk_score"])

(REPORTS/"master_analysis.json").write_text(
    json.dumps(master,indent=2,ensure_ascii=False),
    encoding="utf8"
)

print("="*70)
print("MASTER ANALYSIS GENERATED")
print("Modules:",len(master))
print("Saved:",REPORTS/"master_analysis.json")
print("="*70)
