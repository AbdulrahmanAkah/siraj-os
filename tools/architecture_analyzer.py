import json
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"

graph = json.loads((REPORTS/"dependency_graph.json").read_text(encoding="utf8"))
project = json.loads((REPORTS/"project_index.json").read_text(encoding="utf8"))

# ==========================================================
# Reverse dependency map
# ==========================================================

reverse = defaultdict(list)

for module,deps in graph.items():
    for dep in deps:
        reverse[dep].append(module)

# ==========================================================
# Dead modules
# ==========================================================

dead=[]

for module in graph:
    if len(reverse[module])==0:
        dead.append(module)

(REPORTS/"dead_code.json").write_text(
    json.dumps(sorted(dead),indent=2,ensure_ascii=False),
    encoding="utf8"
)

# ==========================================================
# Circular dependencies
# ==========================================================

cycles=[]

for a,deps in graph.items():
    for b in deps:
        if b in graph and a in graph[b] and a!=b:
            pair=sorted([a,b])
            if pair not in cycles:
                cycles.append(pair)

(REPORTS/"circular_dependencies.json").write_text(
    json.dumps(cycles,indent=2,ensure_ascii=False),
    encoding="utf8"
)

# ==========================================================
# Layer violations
# ==========================================================

violations=[]

for module,deps in graph.items():

    if module.startswith("domain."):

        for dep in deps:

            if dep.startswith("application.") or dep.startswith("infrastructure."):

                violations.append({
                    "module":module,
                    "depends_on":dep
                })

(REPORTS/"layer_violations.json").write_text(
    json.dumps(violations,indent=2,ensure_ascii=False),
    encoding="utf8"
)

# ==========================================================
# Statistics
# ==========================================================

stats={
    "files":len(project),
    "modules":len(graph),
    "imports":sum(len(v) for v in graph.values()),
    "dead_modules":len(dead),
    "cycles":len(cycles),
    "layer_violations":len(violations)
}

(REPORTS/"statistics.json").write_text(
    json.dumps(stats,indent=2,ensure_ascii=False),
    encoding="utf8"
)

# ==========================================================
# Summary
# ==========================================================

summary=f"""
# SIRAJ Architecture Summary

Files: {stats['files']}
Modules: {stats['modules']}
Imports: {stats['imports']}

Dead Modules: {stats['dead_modules']}
Circular Dependencies: {stats['cycles']}
Layer Violations: {stats['layer_violations']}
"""

(REPORTS/"architecture_summary.md").write_text(summary,encoding="utf8")

print("="*70)
print("ARCHITECTURE ANALYSIS COMPLETE")
print("="*70)
print(json.dumps(stats,indent=2))
print("="*70)
