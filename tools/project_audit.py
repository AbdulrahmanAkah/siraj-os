import ast
from dataclasses import dataclass, field
from typing import Dict, List, Set
from pathlib import Path
import re
from collections import defaultdict


@dataclass
class ModuleInfo:
    path: Path
    imports: Set[str] = field(default_factory=set)
    classes: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)

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

import_map = defaultdict(set)

for f in Path("src").rglob("*.py"):

    txt = f.read_text(encoding="utf8")

    for line in txt.splitlines():

        line=line.strip()

        if line.startswith("from "):
            import_map[str(f)].add(line)

        if line.startswith("import "):
            import_map[str(f)].add(line)

for file, imps in sorted(import_map.items()):

    print()
    print(file)

    for imp in sorted(imps):
        print("   ",imp)


def parse_module(path: Path) -> ModuleInfo:
    """Parses a Python module using AST instead of regex."""

    info = ModuleInfo(path=path)

    try:
        source = path.read_text(encoding="utf8")
    except Exception:
        return info

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return info

    for node in ast.walk(tree):

        if isinstance(node, ast.Import):
            for alias in node.names:
                info.imports.add(alias.name)

        elif isinstance(node, ast.ImportFrom):

            module = node.module or ""

            if node.level:
                module = "." * node.level + module

            info.imports.add(module)

        elif isinstance(node, ast.ClassDef):
            info.classes.append(node.name)

        elif isinstance(node, ast.FunctionDef):
            info.functions.append(node.name)

    return info
print()
print("="*120)
print("REAL DUPLICATES")
print("="*120)

for cls, files in sorted(classes.items()):

    if len(files) < 2:
        continue

    print(f"\n{cls}")

    for f in files:

        module = (
            Path(f)
            .with_suffix("")
            .as_posix()
            .replace("/", ".")
        )

        users = []

        for file, file_imports in import_map.items():

            for imp in file_imports:

                if module in imp:
                    users.append(file)

        print(f"  {f}")

        if users:
            for u in users:
                print("      used by ->", u)
        else:
            print("      UNUSED")
