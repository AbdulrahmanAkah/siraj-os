from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"

master = json.loads((REPORTS/"master_analysis.json").read_text(encoding="utf8"))
symbols = json.loads((REPORTS/"symbol_analysis.json").read_text(encoding="utf8"))

class_refs = set(symbols.get("class_references", []))
func_refs = set(symbols.get("function_calls", []))
ctor_refs = set(symbols.get("constructor_calls", []))

verified=[]

for m in master:

    score=m["risk_score"]

    if m["module"]=="main":
        score+=100

    if m["module"].startswith("test_"):
        score-=50

    for c in m["duplicates"]:
        if c in class_refs:
            score+=25

    if m["classes"]>0:
        score+=len(class_refs.intersection(m["duplicates"]))*10

    if score<=0:
        state="SAFE_DELETE"
    elif score<40:
        state="REVIEW"
    else:
        state="KEEP"

    x=dict(m)
    x["verified_state"]=state
    x["verified_score"]=score

    verified.append(x)

verified.sort(
    key=lambda x:(x["verified_state"],x["verified_score"])
)

(REPORTS/"verified_dead_code.json").write_text(
    json.dumps(
        verified,
        indent=2,
        ensure_ascii=False
    ),
    encoding="utf8"
)

print("="*70)
print("VERIFIED DEAD CODE GENERATED")
print("="*70)
print("SAFE_DELETE :",sum(x["verified_state"]=="SAFE_DELETE" for x in verified))
print("REVIEW      :",sum(x["verified_state"]=="REVIEW" for x in verified))
print("KEEP        :",sum(x["verified_state"]=="KEEP" for x in verified))
print("="*70)

