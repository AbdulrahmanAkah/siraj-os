#!/usr/bin/env python3
"""
Siraj Symbol Analyzer
=====================

Advanced AST symbol analyzer.

Produces:

- call_graph
- constructor_calls
- class_references
- inheritance
- symbols
- summary

Python 3.13
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]

REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)

SRC_DIRS = [
    ROOT / "src" / "application",
    ROOT / "src" / "domain",
    ROOT / "src" / "infrastructure",
    ROOT / "src" / "interfaces",
    ROOT / "src" / "tests",
]


# ============================================================
# Helpers
# ============================================================

def module_name(path: Path) -> str:
    rel = path.relative_to(ROOT)

    parts = list(rel.parts)

    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]

    if parts[-1] == "__init__":
        parts.pop()

    return ".".join(parts)


def iter_python_files():

    for directory in SRC_DIRS:

        if not directory.exists():
            continue

        for file in directory.rglob("*.py"):

            if "__pycache__" in file.parts:
                continue

            yield file


# ============================================================
# Analyzer
# ============================================================

class SymbolAnalyzer(ast.NodeVisitor):

    def __init__(self, module: str):

        self.module = module

        self.current_class = None
        self.current_function = None

        self.call_graph = defaultdict(set)
        self.constructor_calls = defaultdict(set)
        self.class_references = set()
        self.inheritance = defaultdict(set)

        self.symbols = []

    # --------------------------------------------------------

    def current_scope(self):

        if self.current_class:

            if self.current_function:
                return f"{self.module}.{self.current_class}.{self.current_function}"

            return f"{self.module}.{self.current_class}"

        if self.current_function:
            return f"{self.module}.{self.current_function}"

        return self.module

    # --------------------------------------------------------

    def add_symbol(self, name, kind, line):

        self.symbols.append(
            {
                "module": self.module,
                "name": name,
                "kind": kind,
                "line": line,
            }
        )

    # ========================================================
    # Classes
    # ========================================================

    def visit_ClassDef(self, node: ast.ClassDef):

        self.add_symbol(
            node.name,
            "class",
            node.lineno,
        )

        previous = self.current_class
        self.current_class = node.name

        for base in node.bases:

            if isinstance(base, ast.Name):

                self.inheritance[node.name].add(base.id)

            elif isinstance(base, ast.Attribute):

                self.inheritance[node.name].add(base.attr)

        self.generic_visit(node)

        self.current_class = previous

    # ========================================================
    # Functions
    # ========================================================

    def visit_FunctionDef(self, node: ast.FunctionDef):

        self.add_symbol(
            node.name,
            "function",
            node.lineno,
        )

        previous = self.current_function
        self.current_function = node.name

        self.generic_visit(node)

        self.current_function = previous

    # --------------------------------------------------------

    def visit_AsyncFunctionDef(self, node):

        self.visit_FunctionDef(node)
            # ========================================================
    # Call extraction
    # ========================================================

    def visit_Call(self, node: ast.Call):

        caller = self.current_scope()

        callee = self.resolve_call_name(node.func)

        if callee:

            self.call_graph[caller].add(callee)

            if self.looks_like_constructor(callee):
                self.constructor_calls[caller].add(callee)

        self.generic_visit(node)

    # ========================================================
    # Name / Attribute extraction
    # ========================================================

    def resolve_call_name(self, node):

        # foo()

        if isinstance(node, ast.Name):

            self.class_references.add(node.id)

            return node.id

        # module.foo()

        if isinstance(node, ast.Attribute):

            return self.attribute_name(node)

        # lambda() etc.

        return None

    # --------------------------------------------------------

    def attribute_name(self, node):

        names = []

        current = node

        while isinstance(current, ast.Attribute):

            names.append(current.attr)

            current = current.value

        if isinstance(current, ast.Name):

            names.append(current.id)

        names.reverse()

        full = ".".join(names)

        if names:

            self.class_references.add(names[-1])

        return full

    # ========================================================
    # Constructor detection
    # ========================================================

    @staticmethod
    def looks_like_constructor(name: str):

        if not name:
            return False

        last = name.split(".")[-1]

        if not last:
            return False

        return last[0].isupper()

    # ========================================================
    # Imports
    # ========================================================

    def visit_Import(self, node):

        for alias in node.names:

            self.class_references.add(alias.name)

    # --------------------------------------------------------

    def visit_ImportFrom(self, node):

        if node.module:

            self.class_references.add(node.module)

        for alias in node.names:

            self.class_references.add(alias.name)

    # ========================================================
    # Type hints
    # ========================================================

    def visit_AnnAssign(self, node):

        self.extract_annotation(node.annotation)

        self.generic_visit(node)

    # --------------------------------------------------------

    def visit_arg(self, node):

        if node.annotation:

            self.extract_annotation(node.annotation)

    # --------------------------------------------------------

    def extract_annotation(self, node):

        if isinstance(node, ast.Name):

            self.class_references.add(node.id)

            return

        if isinstance(node, ast.Attribute):

            self.class_references.add(
                self.attribute_name(node)
            )

            return

        if isinstance(node, ast.Subscript):

            self.extract_annotation(node.value)

            if hasattr(node, "slice"):

                self.extract_annotation(node.slice)

            return

        if isinstance(node, ast.Tuple):

            for item in node.elts:

                self.extract_annotation(item)

            return

        if isinstance(node, ast.List):

            for item in node.elts:

                self.extract_annotation(item)

            return
        # ============================================================
# Project analysis
# ============================================================

def analyze_project():

    call_graph = defaultdict(set)
    constructor_calls = defaultdict(set)
    class_references = defaultdict(set)
    inheritance = defaultdict(set)

    symbols = []

    for file in iter_python_files():

        try:

            source = file.read_text(encoding="utf8")

        except Exception:

            continue

        try:

            tree = ast.parse(source)

        except SyntaxError:

            continue

        analyzer = SymbolAnalyzer(module_name(file))

        analyzer.visit(tree)

        symbols.extend(analyzer.symbols)

        for k, v in analyzer.call_graph.items():
            call_graph[k].update(v)

        for k, v in analyzer.constructor_calls.items():
            constructor_calls[k].update(v)

        class_references[analyzer.module].update(
            analyzer.class_references
        )

        for child, parents in analyzer.inheritance.items():
            inheritance[child].update(parents)

    return {

        "call_graph": {
            k: sorted(v)
            for k, v in sorted(call_graph.items())
        },

        "class_references": {
            k: sorted(v)
            for k, v in sorted(class_references.items())
        },

        "constructor_calls": {
            k: sorted(v)
            for k, v in sorted(constructor_calls.items())
        },

        "inheritance": {
            k: sorted(v)
            for k, v in sorted(inheritance.items())
        },

        "symbols": sorted(
            symbols,
            key=lambda x: (
                x["module"],
                x["line"],
                x["name"],
            ),
        ),
    }


# ============================================================
# Summary
# ============================================================

def build_summary(result):

    edge_count = sum(
        len(v)
        for v in result["call_graph"].values()
    )

    constructor_count = sum(
        len(v)
        for v in result["constructor_calls"].values()
    )

    inheritance_count = sum(
        len(v)
        for v in result["inheritance"].values()
    )

    result["summary"] = {

        "symbols": len(result["symbols"]),

        "call_edges": edge_count,

        "constructors": constructor_count,

        "inheritance": inheritance_count,

    }


# ============================================================
# Save
# ============================================================

def save(result):

    output = REPORTS / "symbol_analysis.json"

    output.write_text(

        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        ),

        encoding="utf8",
    )

    return output


# ============================================================
# Main
# ============================================================

def main():

    result = analyze_project()

    build_summary(result)

    output = save(result)

    print("=" * 70)
    print("SYMBOL ANALYSIS COMPLETE")
    print("=" * 70)

    print(
        f"Symbols      : {result['summary']['symbols']}"
    )

    print(
        f"Call edges   : {result['summary']['call_edges']}"
    )

    print(
        f"Constructors : {result['summary']['constructors']}"
    )

    print(
        f"Inheritance  : {result['summary']['inheritance']}"
    )

    print(f"Saved        : {output}")

    print("=" * 70)


if __name__ == "__main__":
    main()