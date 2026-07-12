import ast
from pathlib import Path
from .models import ModuleInfo


def parse_module(path: Path) -> ModuleInfo:

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