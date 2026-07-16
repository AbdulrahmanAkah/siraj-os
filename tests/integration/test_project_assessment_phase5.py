import json

from src.application.cli_v2 import EXIT_CODES, main


def _output(capsys):
    return json.loads(capsys.readouterr().out)


def _prepare(
    tmp_path,
    capsys,
    source_texts,
):
    root = tmp_path / "pilot"

    assert main([
        "--json",
        "project",
        "init",
        "--root",
        str(root),
        "--slug",
        "assessment-pilot",
        "--topic",
        "Assessment pilot",
        "--language",
        "ar",
    ]) == 0
    capsys.readouterr()

    for index, text in enumerate(source_texts):
        source = tmp_path / f"source-{index}.txt"
        source.write_text(text, encoding="utf-8")

        assert main([
            "--json",
            "source",
            "add",
            "--project-root",
            str(root),
            "--file",
            str(source),
            "--title",
            f"Source {index}",
            "--language",
            "ar",
            "--classification",
            "PUBLIC",
        ]) == 0

        added = _output(capsys)
        assert added["data"]["added"] is True

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

    return root


def test_assessment_status_is_blocked_before_run(
    tmp_path,
    capsys,
):
    root = _prepare(
        tmp_path,
        capsys,
        ["وقعت المعركة سنة 1914 واستمرت طويلاً."],
    )

    result = main([
        "--json",
        "assessment",
        "status",
        "--project-root",
        str(root),
    ])

    payload = _output(capsys)

    assert result == EXIT_CODES["BLOCKED"]
    assert payload["data"]["status"] == "NOT_RUN"


def test_single_source_claim_creates_research_gap(
    tmp_path,
    capsys,
):
    root = _prepare(
        tmp_path,
        capsys,
        ["تأسست المدينة سنة 1901 وبدأ نموها سريعاً."],
    )

    assert main([
        "--json",
        "project",
        "assess",
        "--root",
        str(root),
    ]) == 0

    assessment = _output(capsys)

    assert assessment["data"]["assessment_count"] == 1
    assert assessment["data"]["gap_count"] >= 1

    assert main([
        "--json",
        "gaps",
        "list",
        "--project-root",
        str(root),
    ]) == 0

    gaps = _output(capsys)["data"]["gaps"]

    assert any(
        item["gap_type"] == "SINGLE_SOURCE"
        for item in gaps
    )


def test_independent_sources_raise_claim_support(
    tmp_path,
    capsys,
):
    shared = "بدأ الحدث سنة 1914 واستمر عدة سنوات."

    root = _prepare(
        tmp_path,
        capsys,
        [
            shared,
            shared + "\nيحتوي المصدر الثاني على سياق إضافي.",
        ],
    )

    assert main([
        "--json",
        "project",
        "assess",
        "--root",
        str(root),
    ]) == 0
    capsys.readouterr()

    assessments = json.loads(
        (
            root
            / "working"
            / "assessment"
            / "claim-assessments.json"
        ).read_text(encoding="utf-8")
    )["assessments"]

    shared_assessment = next(
        item
        for item in assessments
        if item["claim_text"] == shared
    )

    assert (
        shared_assessment["status"]
        == "MULTI_SOURCE_SUPPORTED"
    )
    assert shared_assessment["independent_source_count"] == 2
    assert shared_assessment["confidence_level"] == "HIGH"


def test_numeric_conflict_is_detected(
    tmp_path,
    capsys,
):
    root = _prepare(
        tmp_path,
        capsys,
        [
            "تأسست المدينة سنة 1901 وبدأ نموها سريعاً.",
            (
                "تأسست المدينة سنة 1902 وبدأ نموها سريعاً.\n"
                "هذا مصدر مختلف ومستقل."
            ),
        ],
    )

    assert main([
        "--json",
        "project",
        "assess",
        "--root",
        str(root),
    ]) == 0

    result = _output(capsys)

    assert result["data"]["contradiction_count"] == 1

    assert main([
        "--json",
        "contradictions",
        "list",
        "--project-root",
        str(root),
    ]) == 0

    contradictions = _output(capsys)["data"]["contradictions"]

    assert contradictions[0]["contradiction_type"] == "NUMERIC_CONFLICT"
    assert set(contradictions[0]["differing_values"]) == {
        "1901",
        "1902",
    }


def test_assessment_is_deterministic(
    tmp_path,
    capsys,
):
    root = _prepare(
        tmp_path,
        capsys,
        ["وقع الحدث سنة 1945 وانتهت المرحلة لاحقاً."],
    )

    assert main([
        "--json",
        "project",
        "assess",
        "--root",
        str(root),
    ]) == 0
    first = _output(capsys)

    assert main([
        "--json",
        "project",
        "assess",
        "--root",
        str(root),
    ]) == 0
    second = _output(capsys)

    assert (
        first["data"]["assessment_run_id"]
        == second["data"]["assessment_run_id"]
    )
    assert first["data"]["gap_count"] == second["data"]["gap_count"]


def test_assessment_verify_passes_for_intact_artifacts(
    tmp_path,
    capsys,
):
    root = _prepare(
        tmp_path,
        capsys,
        ["أعلن الملك فيصل القرار سنة 1921."],
    )

    assert main([
        "--json",
        "project",
        "assess",
        "--root",
        str(root),
    ]) == 0
    capsys.readouterr()

    result = main([
        "--json",
        "assessment",
        "verify",
        "--project-root",
        str(root),
    ])

    payload = _output(capsys)

    assert result == EXIT_CODES["SUCCESS"]
    assert payload["data"]["status"] == "VALID"
    assert payload["data"]["issues"] == []


def test_assessment_verify_detects_tampered_count(
    tmp_path,
    capsys,
):
    root = _prepare(
        tmp_path,
        capsys,
        ["وقع الحدث سنة 1960 في العاصمة."],
    )

    assert main([
        "--json",
        "project",
        "assess",
        "--root",
        str(root),
    ]) == 0
    capsys.readouterr()

    result_path = (
        root
        / "working"
        / "assessment"
        / "assessment-result.json"
    )

    payload = json.loads(
        result_path.read_text(encoding="utf-8")
    )
    payload["assessment_count"] = 999

    result_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    result = main([
        "--json",
        "assessment",
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

    assert "ASSESSMENT_RESULT_COUNT_MISMATCH" in codes
