import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"

master = json.loads((REPORTS/"master_analysis.json").read_text(encoding="utf8"))

safe = []
review = []
never = []

for item in master:

    if item["path"] == "main.py":
        never.append(item)
        continue

    if item["path"].startswith("cli/"):
        never.append(item)
        continue

    if item["incoming"] > 0:
        never.append(item)
        continue

    if item["dead_candidate"]:

        if item["duplicates"]:
            review.append(item)

        elif item["outgoing"] > 10:
            review.append(item)

        else:
            safe.append(item)

    else:
        review.append(item)

safe.sort(key=lambda x: x["path"])
review.sort(key=lambda x: x["path"])
never.sort(key=lambda x: x["path"])

(REPORTS/"safe_delete.json").write_text(
    json.dumps(safe, indent=2, ensure_ascii=False),
    encoding="utf8"
)

(REPORTS/"review_first.json").write_text(
    json.dumps(review, indent=2, ensure_ascii=False),
    encoding="utf8"
)

(REPORTS/"never_delete.json").write_text(
    json.dumps(never, indent=2, ensure_ascii=False),
    encoding="utf8"
)

print("="*70)
print("SAFE CLEANUP PLAN GENERATED")
print("="*70)
print("SAFE DELETE :", len(safe))
print("REVIEW      :", len(review))
print("KEEP        :", len(never))
print("="*70)
