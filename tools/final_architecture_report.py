
import json
from pathlib import Path

REPORTS=Path("reports")

plan=json.loads((REPORTS/"execution_plan.json").read_text(encoding="utf8"))

lines=[]

lines.append("="*70)
lines.append("FINAL ARCHITECTURE REPORT")
lines.append("="*70)
lines.append("")

for key in ["DELETE","MERGE","RENAME","KEEP","REVIEW"]:

    lines.append(f"{key}: {len(plan[key])}")
    lines.append("")

    for item in plan[key]:
        lines.append(item["module"])

    lines.append("")

(REPORTS/"FINAL_ARCHITECTURE_REPORT.txt").write_text(
    "\n".join(lines),
    encoding="utf8"
)

print("="*70)
print("FINAL REPORT GENERATED")
print("="*70)
