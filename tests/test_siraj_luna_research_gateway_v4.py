import json
import sqlite3
from pathlib import Path

import pytest

from src.application.siraj_luna_research_gateway_v4 import (
    ResearchGatewayV4,
)
from src.application.siraj_luna_iterative_research_v4 import (
    LunaResearchLoopError,
    execute_luna_research_actions,
    validate_luna_research_plan,
)

def _make_repo(tmp_path):
    repo = tmp_path
    db = repo / "book.sqlite"
    con = sqlite3.connect(db)
    try:
        con.execute("CREATE TABLE pages (nass TEXT)")
        con.executemany(
            "INSERT INTO pages(nass) VALUES (?)",
            [
                ("سياق سابق عن آدم",),
                ("ثم وسوس إليه الشيطان",),
                ("فأكلا منها وبدت لهما سوآتهما",),
                ("ثم اجتباه ربه فتاب عليه وهدى",),
            ],
        )
        con.commit()
    finally:
        con.close()
    shortlist = {
        "installations": [
            {
                "books": [
                    {
                        "book_database": str(db),
                        "book_id": 77,
                        "title": "تفسير تجريبي",
                        "author": "مؤلف",
                        "category": "تفسير",
                        "documentary_score": 90,
                        "metadata_excerpt": "آدم الوسوسة التوبة",
                    }
                ]
            }
        ]
    }
    target = repo / "sources/shamela/shamela-dynamic-targeted-shortlist.json"
    target.parent.mkdir(parents=True)
    target.write_text(
        json.dumps(shortlist, ensure_ascii=False),
        encoding="utf-8",
    )
    return repo

def test_search_and_expand_shamela(tmp_path):
    repo = _make_repo(tmp_path)
    gateway = ResearchGatewayV4(repo)
    result = gateway.search_shamela("وسوس آدم")
    assert result["status"] == "PASS"
    assert result["hit_count"] >= 1
    locator = result["hits"][0]["locator"]
    expanded = gateway.expand_shamela_locator(
        locator, before=1, after=1
    )
    assert expanded["status"] == "PASS"
    assert any(row["is_anchor_row"] for row in expanded["rows"])

def test_hadith_search_does_not_claim_authentication(tmp_path):
    repo = _make_repo(tmp_path)
    gateway = ResearchGatewayV4(repo)
    result = gateway.search_hadith_local("آدم")
    assert result["authentication_required"] is True

def test_network_materialization_is_blocked_by_default(tmp_path):
    repo = _make_repo(tmp_path)
    gateway = ResearchGatewayV4(repo)
    with pytest.raises(Exception):
        gateway.materialize_quran_locator(
            "2:36", allow_network=False
        )

def test_luna_plan_must_own_research():
    with pytest.raises(LunaResearchLoopError):
        validate_luna_research_plan(
            {
                "stage_owner": "OTHER",
                "status": "CONTINUE_RESEARCH",
                "research_questions": ["سؤال"],
                "actions": [],
            }
        )

def test_execute_plan_uses_gateway(tmp_path):
    repo = _make_repo(tmp_path)
    plan = {
        "stage_owner": "LUNA",
        "status": "CONTINUE_RESEARCH",
        "research_questions": ["كيف وقعت الوسوسة؟"],
        "coverage_assessment_ar": "نحتاج نصوصا محلية.",
        "actions": [
            {
                "operation": "SEARCH_SHAMELA",
                "purpose_ar": "العثور على مواضع الوسوسة",
                "query": "وسوس آدم",
            }
        ],
        "unresolved_gaps_ar": [],
    }
    out = execute_luna_research_actions(repo, plan)
    assert out["outputs"][0]["result"]["status"] == "PASS"

def test_short_meaningful_shamela_passage_is_searchable_v43(tmp_path):
    repo = _make_repo(tmp_path)
    db = repo / "short-v43.sqlite"
    con = sqlite3.connect(db)
    try:
        con.execute("CREATE TABLE pages (nass TEXT)")
        con.execute(
            "INSERT INTO pages(nass) VALUES (?)",
            ("وسوس آدم",),
        )
        con.commit()
    finally:
        con.close()

    shortlist_path = (
        repo / "sources/shamela/shamela-dynamic-targeted-shortlist.json"
    )
    shortlist = json.loads(shortlist_path.read_text(encoding="utf-8"))
    shortlist["installations"][0]["books"].insert(
        0,
        {
            "book_database": str(db),
            "book_id": 78,
            "title": "مصدر قصير تجريبي",
            "author": "مؤلف",
            "category": "تفسير",
            "documentary_score": 99,
            "metadata_excerpt": "وسوس آدم",
        },
    )
    shortlist_path.write_text(
        json.dumps(shortlist, ensure_ascii=False),
        encoding="utf-8",
    )

    result = ResearchGatewayV4(repo).search_shamela("وسوس آدم")
    assert result["status"] == "PASS"
    assert any(
        hit["book_id"] == 78 and "وسوس آدم" in hit["text"]
        for hit in result["hits"]
    )
