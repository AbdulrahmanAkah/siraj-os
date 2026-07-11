import json
from pathlib import Path

p = Path("reports/dependency_graph_ast.json")

obj = json.loads(p.read_text(encoding="utf8"))

print("="*70)
print("TYPE:", type(obj).__name__)

if isinstance(obj, dict):

    print("KEY COUNT:", len(obj))
    print()

    keys = list(obj.keys())[:10]

    print("FIRST KEYS:")
    for k in keys:
        print(" -", k)

    print()

    first = keys[0]

    print("FIRST VALUE TYPE:", type(obj[first]).__name__)

    if isinstance(obj[first], list):

        print("FIRST VALUE LENGTH:", len(obj[first]))

        if obj[first]:
            print("FIRST ITEM:")
            print(obj[first][0])

    elif isinstance(obj[first], dict):

        print(obj[first])

elif isinstance(obj, list):

    print("LIST LENGTH:", len(obj))

    if obj:
        print("FIRST ELEMENT TYPE:", type(obj[0]).__name__)
        print(obj[0])

print("="*70)
