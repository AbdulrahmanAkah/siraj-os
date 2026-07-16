import os
import subprocess
import sys


def test_cli_repository_path_persists_the_generated_graph(tmp_path):
    source_file = tmp_path / "history.txt"
    source_file.write_text(
        "Muhammad traveled to Makkah in 610. The source is History Book.",
        encoding="utf-8",
    )
    repository_path = tmp_path / "repository"
    environment = os.environ.copy()
    environment.pop("OPENAI_API_KEY", None)
    environment.pop("GEMINI_API_KEY", None)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli.generate",
            "Muhammad",
            str(source_file),
            "--repository",
            str(repository_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (repository_path / "graph.json").exists()
    assert (repository_path / "metadata.json").exists()
    assert '"type": "EVIDENCE"' in result.stdout
