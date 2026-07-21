import json
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime


SHAMELA_DB = Path(r"C:\shamela4\database\master.db")
OUTPUT = Path(
    r"C:\SIRAJ\Repositories\siraj-os\artifacts\shamela\tests\bidaya_4445"
)

BOOK_ID = 4445
SAMPLE_SIZE = 10


def sha256(text):
    return hashlib.sha256(
        text.encode("utf-8", errors="ignore")
    ).hexdigest()


def load_book_metadata():
    con = sqlite3.connect(SHAMELA_DB)
    cur = con.cursor()

    row = cur.execute(
        """
        SELECT book_id, book_name, authors
        FROM book
        WHERE book_id = ?
        """,
        (BOOK_ID,)
    ).fetchone()

    con.close()

    if not row:
        raise RuntimeError(
            f"Book {BOOK_ID} not found"
        )

    return {
        "book_id": row[0],
        "book_title": row[1],
        "authors": row[2],
    }


def discover_storage():
    """
    First validation only.
    Actual body extraction bridge will be attached after confirming storage.
    """

    candidates = []

    store = Path(r"C:\shamela4\database\store")

    for p in store.rglob("*"):
        if p.is_file():
            candidates.append(str(p))

    return candidates[:50]


def main():

    OUTPUT.mkdir(
        parents=True,
        exist_ok=True
    )

    metadata = load_book_metadata()

    candidates = discover_storage()

    source = {
        "source_id": f"shamela-{BOOK_ID}",
        "created_at": datetime.utcnow().isoformat(),
        "metadata": metadata,
        "storage_candidates": candidates
    }

    (OUTPUT / "source_metadata.json").write_text(
        json.dumps(
            source,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


    segments = []

    for i in range(SAMPLE_SIZE):

        segments.append(
            {
                "source_id":
                    f"shamela-{BOOK_ID}",

                "book_id":
                    BOOK_ID,

                "segment_id":
                    f"{BOOK_ID}-{i+1:06d}",

                "locator":
                    {
                        "sample_index": i + 1
                    },

                "original_text":
                    "",

                "source_text_hash":
                    sha256("")
            }
        )


    with open(
        OUTPUT / "raw_segments.jsonl",
        "w",
        encoding="utf-8"
    ) as f:

        for item in segments:
            f.write(
                json.dumps(
                    item,
                    ensure_ascii=False
                )
                + "\n"
            )


    manifest = {
        "status":
            "EXTRACTION_SCAFFOLD_READY",

        "book_id":
            BOOK_ID,

        "segments_created":
            SAMPLE_SIZE,

        "next_step":
            "attach_body_store_reader"
    }


    (OUTPUT / "extraction_manifest.json").write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


    print(json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2
    ))


if __name__ == "__main__":
    main()

