
import json
from pathlib import Path
from collections import deque

REPORTS = Path("reports")

graph = json.loads((REPORTS/"execution_graph.json").read_text(encoding="utf8"))

chains = []

for root,data in graph.items():

    if not data["root"]:
        continue

    q = deque([[root]])

    while q:
        chain = q.popleft()
        last = chain[-1]

        nxt = graph[last]["calls"]

        if not nxt:
            chains.append(chain)
            continue

        for node in nxt:
            if node in chain:
                continue
            q.append(chain+[node])

(REPORTS/"call_chains.json").write_text(
    json.dumps(chains,indent=2,ensure_ascii=False),
    encoding="utf8"
)

print("CALL CHAINS:",len(chains))
