import json
from pathlib import Path


REPORT_DIR = Path("reports")

REPORT_DIR.mkdir(exist_ok=True)


def write_report(name, data):

    with open(
        REPORT_DIR / name,
        "w",
        encoding="utf8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=4,
            default=str
        )
    

def write_json(name, data):
    write_report(name, data)
