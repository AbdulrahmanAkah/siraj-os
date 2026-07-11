import ast
import json
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
REPORTS = ROOT / "reports"

modules={}

for f in SRC.rglob("*.py"):
    mod=".".join(f.relative_to(SRC).with_suffix("").parts)
    modules[mod]=f

graph={}
reverse=defaultdict(list)

for mod,file in modules.items():

    tree=ast.parse(file.read_text(encoding="utf8",errors="ignore"))

    deps=set()

    for node in ast.walk(tree):

        if isinstance(node,ast.Import):

            for n in node.names:

                name=n.name

                for m in modules:
                    if name==m or name.startswith(m+"."):
                        deps.add(m)

        elif isinstance(node,ast.ImportFrom):

            if node.module:

                name=node.module

                for m in modules:
                    if name==m or name.startswith(m+"."):
                        deps.add(m)

    graph[mod]=sorted(deps)

for m,deps in graph.items():
    for d in deps:
        reverse[d].append(m)

dead=sorted([m for m in modules if len(reverse[m])==0])

(REPORTS/"dependency_graph_ast.json").write_text(
    json.dumps(graph,indent=2,ensure_ascii=False),
    encoding="utf8"
)

(REPORTS/"reverse_dependency_graph.json").write_text(
    json.dumps(reverse,indent=2,ensure_ascii=False),
    encoding="utf8"
)

(REPORTS/"dead_candidates.json").write_text(
    json.dumps(dead,indent=2,ensure_ascii=False),
    encoding="utf8"
)

print("="*70)
print("Dependency Graph Updated")
print("Modules :",len(graph))
print("Dead Candidates :",len(dead))
print("Reports:")
print(" - dependency_graph_ast.json")
print(" - reverse_dependency_graph.json")
print(" - dead_candidates.json")
print("="*70)
