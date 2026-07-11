
import json
import shutil
from pathlib import Path
from datetime import datetime

ROOT = Path.cwd()
REPORTS = ROOT / "reports"

plan = json.loads((REPORTS/"execution_plan.json").read_text(encoding="utf8"))

class RefactorEngine:

    def __init__(self):
        self.plan = plan
        self.backup = ROOT.parent / ("siraj_backup_" + datetime.now().strftime("%Y%m%d_%H%M%S"))

    def backup_project(self):
        print("\\n[1/4] BACKUP")
        shutil.copytree(ROOT, self.backup, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"))
        print("Backup:", self.backup)

    def validate_plan(self):
        print("\\n[2/4] VALIDATION")

        validated = []

        for group in ["DELETE","MERGE","RENAME","KEEP","REVIEW"]:
            for item in self.plan[group]:
                item = dict(item)
                item["validated"] = False

                module = item.get("module","")
                src = ROOT / "src" / Path(*module.split("."))

                py = src.with_suffix(".py")

                if py.exists():
                    item["validated"] = True

                validated.append(item)

        (REPORTS/"validated_plan.json").write_text(
            json.dumps(validated,indent=2,ensure_ascii=False),
            encoding="utf8"
        )

        print("Validated:", sum(x["validated"] for x in validated))

    def dry_run(self):
        print("\\n[3/4] DRY RUN")

        validated = json.loads((REPORTS/"validated_plan.json").read_text(encoding="utf8"))

        preview = {
            "delete":[x for x in validated if x["decision"]=="DELETE" and x["validated"]],
            "merge":[x for x in validated if x["decision"]=="MERGE" and x["validated"]],
            "rename":[x for x in validated if x["decision"]=="RENAME" and x["validated"]],
        }

        (REPORTS/"dry_run.json").write_text(
            json.dumps(preview,indent=2,ensure_ascii=False),
            encoding="utf8"
        )

        print("DELETE :",len(preview["delete"]))
        print("MERGE  :",len(preview["merge"]))
        print("RENAME :",len(preview["rename"]))

    def execute(self):
        print("\\n[4/4] EXECUTE")

        print("SAFE MODE ENABLED")
        print("No files modified.")
        print("Remove SAFE MODE manually when you are ready.")

    def run(self):
        self.backup_project()
        self.validate_plan()
        self.dry_run()
        self.execute()

RefactorEngine().run()
