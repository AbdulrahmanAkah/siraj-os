from pathlib import Path

p = Path("tools/reachability_engine.py")

text = p.read_text(encoding="utf8")

if 'reachability.json' not in text:

    marker = 'print("="*70)'

    block = '''

import json
from pathlib import Path

REPORTS = Path(__file__).resolve().parents[1] / "reports"

(REPORTS/"reachability.json").write_text(
    json.dumps(
        {
            "roots": sorted(list(roots)),
            "reachable": sorted(list(reachable)),
            "unreachable": sorted(list(unreachable)),
            "orphans": sorted(list(orphans))
        },
        indent=2,
        ensure_ascii=False
    ),
    encoding="utf8"
)

'''

    text = text.replace(marker, block + "\n" + marker, 1)

    p.write_text(text, encoding="utf8")

print("="*70)
print("reachability_engine patched.")
print("="*70)
