import sqlite3
import json
import re
from pathlib import Path
from datetime import datetime, timezone


BOOK_ID = "4445"

BOOK_ROOT = Path(
    r"C:\shamela4\database\book"
)

OUTPUT = Path(
    r"C:\SIRAJ\Repositories\siraj-os\artifacts\shamela\tests\book_4445_python"
)


ARABIC_RE = re.compile(r"[\u0600-\u06FF]")


def contains_arabic(value):
    if not isinstance(value, str):
        return False
    return bool(ARABIC_RE.search(value))


def find_book_file():

    matches = []

    for p in BOOK_ROOT.rglob("*.db"):
        if p.stem == BOOK_ID:
            matches.append(p)

    return matches


def inspect_database(db_path):

    result = {
        "database": str(db_path),
        "tables": [],
        "text_candidates": []
    }

    con = sqlite3.connect(db_path)
    cur = con.cursor()

    tables = cur.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
        """
    ).fetchall()

    for (table,) in tables:

        table_info = {
            "table": table,
            "columns": []
        }

        columns = cur.execute(
            f"PRAGMA table_info([{table}])"
        ).fetchall()

        for col in columns:

            col_name = col[1]
            col_type = col[2]

            table_info["columns"].append(
                {
                    "name": col_name,
                    "type": col_type
                }
            )

            try:

                rows = cur.execute(
                    f"""
                    SELECT [{col_name}]
                    FROM [{table}]
                    WHERE [{col_name}] IS NOT NULL
                    LIMIT 20
                    """
                ).fetchall()

                for row in rows:

                    value = row[0]

                    if isinstance(value, bytes):

                        try:
                            value = value.decode(
                                "utf-8",
                                errors="ignore"
                            )
                        except:
                            continue

                    if contains_arabic(value):

                        result["text_candidates"].append(
                            {
                                "table": table,
                                "column": col_name,
                                "sample": value[:500],
                                "length": len(value)
                            }
                        )

                        break

            except Exception:
                pass


        result["tables"].append(table_info)

    con.close()

    return result


def extract_samples(db_path, candidate):

    con = sqlite3.connect(db_path)
    cur = con.cursor()

    table = candidate["table"]
    column = candidate["column"]

    rows = cur.execute(
        f"""
        SELECT [{column}]
        FROM [{table}]
        WHERE [{column}] IS NOT NULL
        LIMIT 10
        """
    ).fetchall()

    output = []

    for i,row in enumerate(rows,1):

        value = row[0]

        if isinstance(value, bytes):

            value = value.decode(
                "utf-8",
                errors="ignore"
            )

        output.append(
            {
                "segment_id": i,
                "book_id": BOOK_ID,
                "table": table,
                "column": column,
                "text": value
            }
        )

    con.close()

    return output


def main():

    OUTPUT.mkdir(
        parents=True,
        exist_ok=True
    )

    report = {
        "status": None,
        "book_id": BOOK_ID,
        "time": datetime.now(timezone.utc).isoformat()
    }


    files = find_book_file()

    report["book_files_found"] = [
        str(x) for x in files
    ]


    if not files:

        report["status"] = "BOOK_FILE_NOT_FOUND"

    else:

        db = files[0]

        inspection = inspect_database(db)

        report["inspection"] = inspection


        with open(
            OUTPUT / "database-inspection.json",
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                inspection,
                f,
                ensure_ascii=False,
                indent=2
            )


        if inspection["text_candidates"]:

            candidate = inspection["text_candidates"][0]

            samples = extract_samples(
                db,
                candidate
            )


            with open(
                OUTPUT / "sample-text.json",
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    samples,
                    f,
                    ensure_ascii=False,
                    indent=2
                )


            report["status"] = "TEXT_FOUND"

        else:

            report["status"] = "NO_TEXT_FOUND"



    with open(
        OUTPUT / "report.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            report,
            f,
            ensure_ascii=False,
            indent=2
        )


    print(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2
        )
    )


if __name__ == "__main__":
    main()

