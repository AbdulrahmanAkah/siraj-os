
import json
from pathlib import Path

REPORTS=Path("reports")

plan=json.loads((REPORTS/"architecture_optimizer.json").read_text(encoding="utf8"))

delete=[]
merge=[]
rename=[]
keep=[]
review=[]

for x in plan:
    d=x["decision"]

    if d=="DELETE":
        delete.append(x)

    elif d=="MERGE":
        merge.append(x)

    elif d=="RENAME":
        rename.append(x)

    elif d=="KEEP":
        keep.append(x)

    else:
        review.append(x)

summary={
    "DELETE":delete,
    "MERGE":merge,
    "RENAME":rename,
    "KEEP":keep,
    "REVIEW":review
}

(REPORTS/"execution_plan.json").write_text(
    json.dumps(summary,indent=2,ensure_ascii=False),
    encoding="utf8"
)

print("DELETE",len(delete))
print("MERGE",len(merge))
print("RENAME",len(rename))
print("KEEP",len(keep))
print("REVIEW",len(review))
