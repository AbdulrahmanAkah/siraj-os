import json
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]

data = json.loads(
    (ROOT/"reports"/"project_index.json").read_text(encoding="utf8")
)

duplicates = defaultdict(list)

for f in data:

    for cls in f["classes"]:

        duplicates[cls].append(f["module"])

real_duplicates = {
    k:v
    for k,v in duplicates.items()
    if len(v)>1
}

output = ROOT/"reports"/"duplicate_symbols.json"

output.write_text(
    json.dumps(real_duplicates,indent=2,ensure_ascii=False),
    encoding="utf8"
)

print("="*60)
print("Duplicate class report generated.")
print("Duplicate Classes:",len(real_duplicates))
print(output)
print("="*60)
