from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)

def run(cmd):
    try:
        r = subprocess.run(
            cmd,
            cwd=ROOT,
            capture_output=True,
            text=True
        )
        return {
            "returncode": r.returncode,
            "stdout": r.stdout,
            "stderr": r.stderr
        }
    except Exception as e:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": str(e)
        }

def load_json(name):
    p = REPORTS / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf8"))
    except:
        return None

auditor = run([sys.executable, "tools/project_auditor.py"])

missing = load_json("missing_imports.json") or {}
stats = load_json("statistics.json") or {}

summary = {
    "auditor_success": auditor["returncode"] == 0,
    "missing_import_modules": len(missing),
    "missing_import_entries": sum(len(v) for v in missing.values()) if isinstance(missing, dict) else 0,
    "statistics": stats
}

(REPORTS / "project_health.json").write_text(
    json.dumps(summary, indent=4, ensure_ascii=False),
    encoding="utf8"
)

print("=" * 60)
print("PROJECT HEALTH")
print("=" * 60)

for k, v in summary.items():
    print(f"{k:30} {v}")
