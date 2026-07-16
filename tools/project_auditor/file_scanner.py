from pathlib import Path

def scan_python_files(root="src"):

    return sorted(Path(root).rglob("*.py"))