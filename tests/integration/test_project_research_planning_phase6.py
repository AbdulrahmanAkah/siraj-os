import json

from src.application.cli_v2 import EXIT_CODES, main


def _output(capsys):
    return json.loads(capsys.readouterr().out)


def _prepare(
    tmp_path,
    capsys,
    texts,
):
    root = tmp_path / "pilot"

    assert main([
        "--json",
        "project",
        "init",
        "--root",
        str(root),
        "--slug",
        "research-planning-pilot",
        "--topic",
        "Research planning pilot",
        "--language",
        "ar",
    ]) == 0
    capsys.readouterr()

    for index, text in enumerate(texts):
        source = tmp_path / f"source-{index}.txt"
        source.write_text(
            text,
            encoding="utf-8",
        )

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
        "project",
        "assess",
        "--root",
        str(root),
    ]) == 0
    capsys.readouterr()

    return root


def test_research_status_is_blocked_before_planning(
    tmp_path,
    capsys,
):
    root = _prepare(
        tmp_path,
        capsys,
        ["تأسست المدينة سنة 1901 وبدأ نموها سريعاً."],
    )

    result = main([
        "--json",
        "research",
        "status",
        "--project-root",
        str(root),
    ])

    payload = _output(capsys)

    assert result == EXIT_CODES["BLOCKED"]
    assert payload["data"]["status"] == "NOT_RUN"


def test_single_source_gap_creates_research_task(
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
        "plan-research",
        "--root",
        str(root),
    ]) == 0

    result = _output(capsys)

    assert result["data"]["task_count"] == 1
    assert result["data"]["query_count"] == 2

    assert main([
        "--json",
        "research",
        "tasks",
        "--project-root",
        str(root),
    ]) == 0

    tasks = _output(capsys)["data"]["tasks"]

    assert tasks[0]["gap_type"] == "SINGLE_SOURCE"
    assert (
        tasks[0]["task_type"]
        == "FIND_CORROBORATING_SOURCE"
    )
    assert tasks[0]["priority"] == "HIGH"
    assert len(tasks[0]["completion_criteria"]) >= 3


def test_research_task_show_includes_queries(
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
        "plan-research",
        "--root",
        str(root),
    ]) == 0
    capsys.readouterr()

    assert main([
        "--json",
        "research",
        "tasks",
        "--project-root",
        str(root),
    ]) == 0

    task = _output(capsys)["data"]["tasks"][0]

    assert main([
        "--json",
        "research",
        "task-show",
        "--project-root",
        str(root),
        "--task-id",
        task["task_id"],
    ]) == 0

    payload = _output(capsys)["data"]

    assert payload["task"]["task_id"] == task["task_id"]
    assert len(payload["queries"]) == len(
        task["query_ids"]
    )


def test_contradiction_gap_creates_resolution_task(
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
                "يقدم المصدر الثاني سياقاً إضافياً."
            ),
        ],
    )

    assert main([
        "--json",
        "project",
        "plan-research",
        "--root",
        str(root),
    ]) == 0
    capsys.readouterr()

    assert main([
        "--json",
        "research",
        "tasks",
        "--project-root",
        str(root),
    ]) == 0

    tasks = _output(capsys)["data"]["tasks"]

    resolution_tasks = [
        item
        for item in tasks
        if item["task_type"]
        == "RESOLVE_CONTRADICTION"
    ]

    assert len(resolution_tasks) == 2
    assert all(
        item["priority"] == "CRITICAL"
        for item in resolution_tasks
    )


def test_research_plan_is_deterministic(
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
        "plan-research",
        "--root",
        str(root),
    ]) == 0

    first = _output(capsys)

    assert main([
        "--json",
        "project",
        "plan-research",
        "--root",
        str(root),
    ]) == 0

    second = _output(capsys)

    assert (
        first["data"]["research_plan_id"]
        == second["data"]["research_plan_id"]
    )
    assert (
        first["data"]["task_count"]
        == second["data"]["task_count"]
    )


def test_research_verify_passes_for_intact_plan(
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
        "plan-research",
        "--root",
        str(root),
    ]) == 0
    capsys.readouterr()

    result = main([
        "--json",
        "research",
        "verify",
        "--project-root",
        str(root),
    ])

    payload = _output(capsys)

    assert result == EXIT_CODES["SUCCESS"]
    assert payload["data"]["status"] == "VALID"
    assert payload["data"]["issues"] == []


def test_research_verify_detects_tampered_task_count(
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
        "plan-research",
        "--root",
        str(root),
    ]) == 0
    capsys.readouterr()

    result_path = (
        root
        / "working"
        / "research"
        / "research-result.json"
    )

    payload = json.loads(
        result_path.read_text(encoding="utf-8")
    )
    payload["task_count"] = 999

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
        "research",
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

    assert "RESEARCH_RESULT_COUNT_MISMATCH" in codes
