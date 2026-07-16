from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"

intel = json.loads((REPORTS/"architecture_intelligence.json").read_text(encoding="utf8"))
reach = json.loads((REPORTS/"reachability_report.json").read_text(encoding="utf8"))

(REPORTS/"reachability.json").write_text(
    json.dumps(reach, indent=2, ensure_ascii=False),
    encoding="utf8"
)

print("="*70)
print("reachability.json created.")
print("="*70)
