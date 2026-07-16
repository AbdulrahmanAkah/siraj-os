from pathlib import Path
import re
from collections import defaultdict

print("="*120)
print("FILES")
print("="*120)

for p in sorted(Path("src").rglob("*.py")):
    print(p)

print()
print("="*120)
print("DUPLICATE CLASSES")
print("="*120)

classes = defaultdict(list)

for f in Path(".").rglob("*.py"):

    try:
        txt = f.read_text(encoding="utf8")
    except:
        continue

    for m in re.finditer(r'^class\s+([A-Za-z_][A-Za-z0-9_]*)', txt, re.M):
        classes[m.group(1)].append(str(f))

for cls, files in sorted(classes.items()):

    if len(files) > 1:
        print()
        print(cls)
        for x in files:
            print("   ", x)

print()
print("="*120)
print("IMPORTS")
print("="*120)

imports = defaultdict(set)

for f in Path("src").rglob("*.py"):

    txt = f.read_text(encoding="utf8")

    for line in txt.splitlines():

        line=line.strip()

        if line.startswith("from "):
            imports[str(f)].add(line)

        if line.startswith("import "):
            imports[str(f)].add(line)

for file, imps in sorted(imports.items()):

    print()
    print(file)

    for imp in sorted(imps):
        print("   ",imp)