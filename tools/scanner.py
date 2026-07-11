from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


@dataclass
class FileInfo:
    path: str
    module: str
    lines: int

    imports: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    dataclasses: list[str] = field(default_factory=list)
    enums: list[str] = field(default_factory=list)

    inheritance: dict[str,list[str]] = field(default_factory=dict)
    decorators: dict[str,list[str]] = field(default_factory=dict)


class ProjectScanner:

    def scan(self):

        result=[]

        for file in SRC.rglob("*.py"):

            result.append(self.scan_file(file))

        return result

    def scan_file(self,file:Path):

        source=file.read_text(
            encoding="utf8",
            errors="ignore"
        )

        tree=ast.parse(source)

        info=FileInfo(
            path=str(file.relative_to(ROOT)),
            module=".".join(file.relative_to(SRC).with_suffix("").parts),
            lines=len(source.splitlines())
        )

        for node in ast.walk(tree):

            if isinstance(node,ast.Import):

                for n in node.names:
                    info.imports.append(n.name)

            elif isinstance(node,ast.ImportFrom):

                mod=node.module or ""

                for n in node.names:
                    info.imports.append(f"{mod}.{n.name}")

            elif isinstance(node,ast.ClassDef):

                info.classes.append(node.name)

                bases=[]

                for b in node.bases:

                    if isinstance(b,ast.Name):
                        bases.append(b.id)

                    elif isinstance(b,ast.Attribute):
                        bases.append(b.attr)

                info.inheritance[node.name]=bases

                dec=[]

                for d in node.decorator_list:

                    if isinstance(d,ast.Name):
                        dec.append(d.id)

                    elif isinstance(d,ast.Attribute):
                        dec.append(d.attr)

                info.decorators[node.name]=dec

                if "dataclass" in dec:
                    info.dataclasses.append(node.name)

                if "Enum" in bases:
                    info.enums.append(node.name)

            elif isinstance(node,ast.FunctionDef):

                info.functions.append(node.name)

        return info


if __name__=="__main__":

    scanner=ProjectScanner()

    files=scanner.scan()

    print("="*60)
    print("FILES:",len(files))
    print("="*60)

    total_classes=sum(len(f.classes) for f in files)
    total_functions=sum(len(f.functions) for f in files)

    print("Classes :",total_classes)
    print("Functions :",total_functions)

    for f in files[:10]:
        print(f.module)
