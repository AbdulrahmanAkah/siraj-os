from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"

master = json.loads((REPORTS/"master_analysis.json").read_text(encoding="utf8"))
verified = json.loads((REPORTS/"verified_dead_code.json").read_text(encoding="utf8"))
duplicates = json.loads((REPORTS/"duplicate_symbols.json").read_text(encoding="utf8"))
orphans = set(json.loads((REPORTS/"orphan_modules.json").read_text(encoding="utf8")))
reachable = set(json.loads((REPORTS/"reachable_modules.json").read_text(encoding="utf8")))

duplicate_modules=set()

for lst in duplicates.values():
    duplicate_modules.update(lst)

result=[]

for m in master:

    module=m["module"]

    decision="KEEP"
    confidence=100
    reasons=[]

    if module in orphans:
        reasons.append("orphan")

    if module not in reachable:
        reasons.append("unreachable")

    if module in duplicate_modules:
        reasons.append("duplicate")

    if m["dead_candidate"]:
        reasons.append("dead_candidate")

    if (
        "dead_candidate" in reasons and
        "orphan" in reasons and
        "unreachable" in reasons
    ):
        decision="DELETE"
        confidence=99

    elif (
        "duplicate" in reasons and
        "unreachable" in reasons
    ):
        decision="MERGE"
        confidence=95

    elif "duplicate" in reasons:
        decision="RENAME"
        confidence=80

    elif "dead_candidate" in reasons:
        decision="REVIEW"
        confidence=60

    result.append({
        "module":module,
        "decision":decision,
        "confidence":confidence,
        "reasons":reasons
    })

(REPORTS/"architecture_intelligence.json").write_text(
    json.dumps(result,indent=2,ensure_ascii=False),
    encoding="utf8"
)

summary={}

for r in result:
    summary[r["decision"]]=summary.get(r["decision"],0)+1

(REPORTS/"architecture_summary.json").write_text(
    json.dumps(summary,indent=2,ensure_ascii=False),
    encoding="utf8"
)

print("="*70)
print("ARCHITECTURE INTELLIGENCE COMPLETE")
print("="*70)

for k,v in sorted(summary.items()):
    print(f"{k:10} : {v}")

print("="*70)
