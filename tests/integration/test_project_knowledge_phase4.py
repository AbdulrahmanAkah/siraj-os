import json

from src.application.cli_v2 import EXIT_CODES, main


def _output(capsys):
    return json.loads(capsys.readouterr().out)


def _prepare_project(tmp_path, capsys, text):
    root = tmp_path / "pilot"
    source = tmp_path / "source.txt"
    source.write_text(text, encoding="utf-8")

    assert main([
        "--json",
        "project",
        "init",
        "--root",
        str(root),
        "--slug",
        "knowledge-pilot",
        "--topic",
        "Historical pilot",
        "--language",
        "ar",
    ]) == 0
    capsys.readouterr()

    assert main([
        "--json",
        "source",
        "add",
        "--project-root",
        str(root),
        "--file",
        str(source),
        "--language",
        "ar",
        "--classification",
        "PUBLIC",
    ]) == 0
    capsys.readouterr()

    assert main([
        "--json",
        "project",
        "ingest",
        "--root",
        str(root),
    ]) == 0
    capsys.readouterr()

    return root


def test_knowledge_status_is_blocked_before_extraction(
    tmp_path,
    capsys,
):
    root = _prepare_project(
        tmp_path,
        capsys,
        "هذا مصدر تاريخي تجريبي.",
    )

    result = main([
        "--json",
        "knowledge",
        "status",
        "--project-root",
        str(root),
    ])

    payload = _output(capsys)

    assert result == EXIT_CODES["BLOCKED"]
    assert payload["data"]["status"] == "NOT_RUN"


def test_project_extract_creates_precise_evidence_and_claims(
    tmp_path,
    capsys,
):
    root = _prepare_project(
        tmp_path,
        capsys,
        (
            "وقعت المعركة سنة 1258 في المدينة.\n"
            "قاد السلطان محمد الجيش إلى الموقع."
        ),
    )

    result = main([
        "--json",
        "project",
        "extract",
        "--root",
        str(root),
    ])

    payload = _output(capsys)

    assert result == EXIT_CODES["SUCCESS"]
    assert payload["data"]["segment_count"] == 2
    assert payload["data"]["evidence_count"] == 2
    assert payload["data"]["claim_count"] == 2
    assert payload["data"]["event_count"] == 1
    assert payload["data"]["entity_count"] >= 1

    knowledge = root / "working" / "knowledge"

    required = {
        "segments.json",
        "evidence.json",
        "claims.json",
        "entities.json",
        "events.json",
        "provenance.json",
        "extraction-result.json",
    }

    assert required.issubset(
        {path.name for path in knowledge.iterdir()}
    )

    evidence = json.loads(
        (knowledge / "evidence.json").read_text(
            encoding="utf-8"
        )
    )["evidence"]

    assert evidence[0]["start_character"] == 0
    assert evidence[0]["end_character"] > evidence[0]["start_character"]
    assert evidence[0]["status"] == "PRESENT_IN_SOURCE"


def test_claims_are_linked_to_existing_evidence(
    tmp_path,
    capsys,
):
    root = _prepare_project(
        tmp_path,
        capsys,
        "تأسست المدينة سنة 1901 وبدأ نموها سريعاً.",
    )

    assert main([
        "--json",
        "project",
        "extract",
        "--root",
        str(root),
    ]) == 0
    capsys.readouterr()

    claims_result = main([
        "--json",
        "claims",
        "list",
        "--project-root",
        str(root),
    ])
    claims = _output(capsys)

    evidence_result = main([
        "--json",
        "evidence",
        "list",
        "--project-root",
        str(root),
    ])
    evidence = _output(capsys)

    assert claims_result == EXIT_CODES["SUCCESS"]
    assert evidence_result == EXIT_CODES["SUCCESS"]

    evidence_ids = {
        item["evidence_id"]
        for item in evidence["data"]["evidence"]
    }

    assert claims["data"]["claim_count"] == 1
    assert set(
        claims["data"]["claims"][0]["evidence_ids"]
    ).issubset(evidence_ids)

    assert (
        claims["data"]["claims"][0]["status"]
        == "SUPPORTED_BY_SOURCE_TEXT"
    )


def test_duplicate_statement_becomes_multi_source_supported(
    tmp_path,
    capsys,
):
    root = _prepare_project(
        tmp_path,
        capsys,
        "بدأ الحدث سنة 1914 واستمر عدة سنوات.",
    )

    second = tmp_path / "second.txt"
    second.write_text(
        (
            'بدأ الحدث سنة 1914 واستمر عدة سنوات.' + "\n" +
            'يقدم هذا المصدر سياقاً إضافياً مستقلاً.'
        ),
        encoding="utf-8",
    )

    assert main([
        "--json",
        "source",
        "add",
        "--project-root",
        str(root),
        "--file",
        str(second),
        "--title",
        "Second source",
    ]) == 0

    added = _output(capsys)
    assert added["data"]["added"] is True
    assert added["data"]["duplicate"] is False

    assert main([
        "--json",
        "project",
        "ingest",
        "--root",
        str(root),
    ]) == 0
    capsys.readouterr()

    assert main([
        "--json",
        "project",
        "extract",
        "--root",
        str(root),
    ]) == 0
    capsys.readouterr()

    assert main([
        "--json",
        "claims",
        "list",
        "--project-root",
        str(root),
    ]) == 0

    payload = _output(capsys)
    claim = next(
        item
        for item in payload["data"]["claims"]
        if item["claim_text"] == 'بدأ الحدث سنة 1914 واستمر عدة سنوات.'
    )

    assert claim["status"] == "MULTI_SOURCE_SUPPORTED"
    assert len(claim["source_ids"]) == 2
    assert len(claim["evidence_ids"]) == 2


def test_knowledge_extraction_is_deterministic(
    tmp_path,
    capsys,
):
    root = _prepare_project(
        tmp_path,
        capsys,
        "وقع الحدث سنة 1945 وانتهت المرحلة.",
    )

    assert main([
        "--json",
        "project",
        "extract",
        "--root",
        str(root),
    ]) == 0

    first = _output(capsys)

    assert main([
        "--json",
        "project",
        "extract",
        "--root",
        str(root),
    ]) == 0

    second = _output(capsys)

    assert (
        first["data"]["extraction_id"]
        == second["data"]["extraction_id"]
    )
    assert first["data"]["claim_count"] == second["data"]["claim_count"]
    assert first["data"]["event_count"] == second["data"]["event_count"]


def test_knowledge_verify_passes_for_intact_artifacts(
    tmp_path,
    capsys,
):
    root = _prepare_project(
        tmp_path,
        capsys,
        "أعلن الملك فيصل القرار سنة 1921.",
    )

    assert main([
        "--json",
        "project",
        "extract",
        "--root",
        str(root),
    ]) == 0
    capsys.readouterr()

    result = main([
        "--json",
        "knowledge",
        "verify",
        "--project-root",
        str(root),
    ])

    payload = _output(capsys)

    assert result == EXIT_CODES["SUCCESS"]
    assert payload["data"]["status"] == "VALID"
    assert payload["data"]["issues"] == []


def test_knowledge_verify_detects_tampered_evidence(
    tmp_path,
    capsys,
):
    root = _prepare_project(
        tmp_path,
        capsys,
        "وقع الحدث سنة 1960 في العاصمة.",
    )

    assert main([
        "--json",
        "project",
        "extract",
        "--root",
        str(root),
    ]) == 0
    capsys.readouterr()

    evidence_path = (
        root
        / "working"
        / "knowledge"
        / "evidence.json"
    )
    payload = json.loads(
        evidence_path.read_text(encoding="utf-8")
    )
    payload["evidence"][0]["text"] = "tampered"

    evidence_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    result = main([
        "--json",
        "knowledge",
        "verify",
        "--project-root",
        str(root),
    ])

    report = _output(capsys)

    assert result == EXIT_CODES["VALIDATION_FAILURE"]
    assert report["data"]["status"] == "INVALID"

    codes = {
        item["code"]
        for item in report["data"]["issues"]
    }

    assert "EVIDENCE_TEXT_MISMATCH" in codes
    assert "EVIDENCE_FINGERPRINT_MISMATCH" in codes
