import json
from pathlib import Path
from src.application.cli_v2 import EXIT_CODES,execute,main
def test_cli_v2_stable_json_and_exit_codes(capsys):
 assert EXIT_CODES["SUCCESS"]==0 and EXIT_CODES["BLOCKED"]==8
 payload=json.loads(execute("health",True));assert payload["status"]=="SUCCESS" and payload["version"]=="0.1.0-rc.2"
 assert main(["version","--json"])==0 and "SUCCESS" in capsys.readouterr().out
def test_release_candidate_package_metadata_and_docs_exist():
 root=Path(__file__).parents[2]
 assert "version = \"0.1.0rc2\"" in (root/"pyproject.toml").read_text()
 assert (root/"README.md").exists() and (root/"docs"/"OPERATIONS_GUIDE.md").exists()
