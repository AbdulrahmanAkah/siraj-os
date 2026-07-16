from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from src.application.operations_common import (
    CANONICAL_TIMESTAMP,
    deterministic_id,
)
from src.application.project_runtime import (
    load_project,
    project_paths,
)
from src.application.rc_hardening import (
    SQLiteConnectionConfig,
    SQLitePersistenceAdapter,
)


RESEARCH_PLAN_SCHEMA_VERSION = "siraj-research-plan-v1"

_PRIORITY_ORDER = {
    "CRITICAL": 0,
    "HIGH": 1,
    "MEDIUM": 2,
    "LOW": 3,
}

_GAP_TASK_TYPES = {
    "PROVENANCE_INTEGRITY": "REPAIR_PROVENANCE",
    "NO_INDEPENDENT_SOURCE": "ACQUIRE_PRIMARY_SOURCE",
    "SINGLE_SOURCE": "FIND_CORROBORATING_SOURCE",
    "CONTRADICTION_REVIEW": "RESOLVE_CONTRADICTION",
    "UNUSED_SOURCE": "REVIEW_UNUSED_SOURCE",
}

_TASK_REQUIREMENTS = {
    "REPAIR_PROVENANCE": (
        "Existing evidence and provenance records",
        "Exact source-to-evidence linkage",
    ),
    "ACQUIRE_PRIMARY_SOURCE": (
        "Primary or authoritative source",
        "Direct textual support for the claim",
    ),
    "FIND_CORROBORATING_SOURCE": (
        "Independent corroborating source",
        "Direct support for the same claim",
    ),
    "RESOLVE_CONTRADICTION": (
        "Sources representing each conflicting value",
        "Contextual explanation or authoritative adjudication",
    ),
    "REVIEW_UNUSED_SOURCE": (
        "Registered source file",
        "Readable and relevant extractable content",
    ),
}

_CHANNELS_BY_TASK = {
    "REPAIR_PROVENANCE": [
        "PROJECT_SOURCE_REGISTRY",
        "PROJECT_EVIDENCE_REGISTRY",
    ],
    "ACQUIRE_PRIMARY_SOURCE": [
        "PUBLIC_ARCHIVE",
        "LIBRARY_CATALOG",
        "ACADEMIC_INDEX",
    ],
    "FIND_CORROBORATING_SOURCE": [
        "ACADEMIC_INDEX",
        "LIBRARY_CATALOG",
        "PUBLIC_ARCHIVE",
    ],
    "RESOLVE_CONTRADICTION": [
        "PRIMARY_SOURCE_COLLECTION",
        "ACADEMIC_INDEX",
        "PUBLIC_ARCHIVE",
    ],
    "REVIEW_UNUSED_SOURCE": [
        "PROJECT_SOURCE_REGISTRY",
    ],
}

_VERIFICATION_BY_TASK = {
    "REPAIR_PROVENANCE": "STRICT_STRUCTURAL_VERIFICATION",
    "ACQUIRE_PRIMARY_SOURCE": "STRICT_SOURCE_VERIFICATION",
    "FIND_CORROBORATING_SOURCE": "STRICT_INDEPENDENCE_VERIFICATION",
    "RESOLVE_CONTRADICTION": "STRICT_CONTRADICTION_REVIEW",
    "REVIEW_UNUSED_SOURCE": "STANDARD_RELEVANCE_VERIFICATION",
}


@dataclass(frozen=True)
class ResearchQuery:
    query_id: str
    task_id: str
    query_text: str
    query_strategy: str
    discovery_channels: list[str]
    verification_requirement: str
    position: int


@dataclass(frozen=True)
class ResearchTask:
    task_id: str
    subject_id: str
    gap_id: str
    gap_type: str
    task_type: str
    title: str
    objective: str
    priority: str
    dependency_ids: list[str]
    completion_criteria: list[str]
    query_ids: list[str]
    position: int
    status: str = "PLANNED"


@dataclass(frozen=True)
class ResearchPlan:
    plan_id: str
    project_id: str
    assessment_run_id: str
    task_ids: list[str]
    query_ids: list[str]
    critical_task_count: int
    task_count: int
    query_count: int
    status: str = "PLANNED"


@dataclass(frozen=True)
class ResearchPlanVerificationIssue:
    code: str
    subject_id: str = ""
    detail: str = ""


@dataclass(frozen=True)
class ResearchPlanVerificationReport:
    project_id: str
    status: str
    task_count: int
    query_count: int
    issues: list[ResearchPlanVerificationIssue]


def _absolute_path(raw: str | Path, field_name: str) -> Path:
    path = Path(raw).expanduser()

    if not path.is_absolute():
        raise ValueError(f"{field_name}_MUST_BE_ABSOLUTE")

    return path.resolve(strict=False)


def _canonical_json(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None

    try:
        handle = tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=".siraj-",
            suffix=".tmp",
            delete=False,
        )
        temporary = handle.name

        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary, path)
    finally:
        if temporary and Path(temporary).exists():
            Path(temporary).unlink(missing_ok=True)


def _write_json(path: Path, payload: Any) -> None:
    _atomic_write(
        path,
        _canonical_json(payload).encode("utf-8"),
    )


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"FILE_NOT_FOUND:{path}")

    try:
        return json.loads(
            path.read_text(encoding="utf-8-sig")
        )
    except json.JSONDecodeError as error:
        raise ValueError(
            f"INVALID_JSON:{path}:{error.lineno}:{error.colno}"
        ) from error


def _assessment_artifact(
    project_root: Path,
    filename: str,
) -> dict[str, Any]:
    paths = project_paths(project_root)
    path = (
        Path(paths.working_root)
        / "assessment"
        / filename
    )
    payload = _read_json(path)

    if (
        payload.get("schema_version")
        != "siraj-claim-assessment-v1"
    ):
        raise ValueError("INVALID_ASSESSMENT_SCHEMA")

    return payload


def _knowledge_artifact(
    project_root: Path,
    filename: str,
) -> dict[str, Any]:
    paths = project_paths(project_root)
    path = (
        Path(paths.working_root)
        / "knowledge"
        / filename
    )
    payload = _read_json(path)

    if (
        payload.get("schema_version")
        != "siraj-knowledge-evidence-v1"
    ):
        raise ValueError("INVALID_KNOWLEDGE_SCHEMA")

    return payload


def _normalise_query_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _claim_lookup(
    claims: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        item["claim_id"]: item
        for item in claims
    }


def _contradiction_lookup(
    contradictions: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}

    for item in contradictions:
        result.setdefault(
            item["claim_a_id"],
            [],
        ).append(item)

        result.setdefault(
            item["claim_b_id"],
            [],
        ).append(item)

    return result


def _task_objective(
    task_type: str,
    subject_id: str,
    subject_text: str,
) -> str:
    if task_type == "REPAIR_PROVENANCE":
        return (
            f"Repair provenance integrity for {subject_id} and confirm "
            "that every evidence reference resolves to its registered source."
        )

    if task_type == "ACQUIRE_PRIMARY_SOURCE":
        return (
            "Acquire an attributable primary or authoritative source "
            f"that directly addresses: {subject_text}"
        )

    if task_type == "FIND_CORROBORATING_SOURCE":
        return (
            "Find an independent source that directly corroborates "
            f"the claim: {subject_text}"
        )

    if task_type == "RESOLVE_CONTRADICTION":
        return (
            "Determine why conflicting claims exist and document "
            f"the correct contextual interpretation for: {subject_text}"
        )

    return (
        f"Review source relevance and extraction quality for {subject_id}."
    )


def _task_title(
    task_type: str,
    subject_id: str,
) -> str:
    titles = {
        "REPAIR_PROVENANCE": "Repair provenance linkage",
        "ACQUIRE_PRIMARY_SOURCE": "Acquire primary source",
        "FIND_CORROBORATING_SOURCE": "Find corroborating source",
        "RESOLVE_CONTRADICTION": "Resolve contradiction",
        "REVIEW_UNUSED_SOURCE": "Review unused source",
    }

    return f"{titles[task_type]}: {subject_id}"


def _query_strategy(task_type: str) -> str:
    strategies = {
        "REPAIR_PROVENANCE": "REGISTRY_TRACE",
        "ACQUIRE_PRIMARY_SOURCE": "CLAIM_AND_PRIMARY_SOURCE",
        "FIND_CORROBORATING_SOURCE": "CLAIM_EXACT_AND_PARAPHRASE",
        "RESOLVE_CONTRADICTION": "CONFLICTING_VALUES_AND_CONTEXT",
        "REVIEW_UNUSED_SOURCE": "SOURCE_RELEVANCE_REVIEW",
    }

    return strategies[task_type]


def _build_query_texts(
    task_type: str,
    subject_text: str,
    contradiction_records: list[dict[str, Any]],
) -> list[str]:
    subject_text = _normalise_query_text(subject_text)

    if task_type == "REPAIR_PROVENANCE":
        return [
            f"Trace evidence and source provenance for: {subject_text}",
        ]

    if task_type == "ACQUIRE_PRIMARY_SOURCE":
        return [
            f'Primary source for "{subject_text}"',
            f'Authoritative historical document about "{subject_text}"',
        ]

    if task_type == "FIND_CORROBORATING_SOURCE":
        return [
            f'Independent source confirming "{subject_text}"',
            f'Academic source discussing "{subject_text}"',
        ]

    if task_type == "RESOLVE_CONTRADICTION":
        values = sorted(
            {
                value
                for record in contradiction_records
                for value in record.get(
                    "differing_values",
                    [],
                )
            }
        )

        value_text = " versus ".join(values)

        return [
            f'Conflicting evidence about "{subject_text}" {value_text}'.strip(),
            f'Authoritative chronology for "{subject_text}"',
        ]

    return [
        f'Review relevance of registered source "{subject_text}"',
    ]


def _completion_criteria(
    task_type: str,
) -> list[str]:
    requirement_a, requirement_b = _TASK_REQUIREMENTS[
        task_type
    ]

    return [
        requirement_a,
        requirement_b,
        "Source identity is recorded",
        "Evidence passage is stored with exact offsets",
        "Assessment is rerun after source ingestion",
    ]


def build_research_plan(
    project_root: str,
) -> dict[str, Any]:
    root = _absolute_path(project_root, "PROJECT_ROOT")
    project = load_project(root)
    paths = project_paths(root)

    gaps_payload = _assessment_artifact(
        root,
        "research-gaps.json",
    )
    assessments_payload = _assessment_artifact(
        root,
        "claim-assessments.json",
    )
    contradictions_payload = _assessment_artifact(
        root,
        "contradictions.json",
    )
    claims_payload = _knowledge_artifact(
        root,
        "claims.json",
    )

    gaps = gaps_payload.get("gaps", [])
    assessments = assessments_payload.get(
        "assessments",
        [],
    )
    contradictions = contradictions_payload.get(
        "contradictions",
        [],
    )
    claims = claims_payload.get("claims", [])

    if not isinstance(gaps, list):
        raise ValueError("INVALID_RESEARCH_GAPS")

    if not gaps:
        raise ValueError("NO_RESEARCH_GAPS")

    claims_by_id = _claim_lookup(claims)
    assessment_by_claim = {
        item["claim_id"]: item
        for item in assessments
    }
    contradictions_by_claim = _contradiction_lookup(
        contradictions
    )

    sorted_gaps = sorted(
        gaps,
        key=lambda item: (
            _PRIORITY_ORDER.get(
                item.get("priority", "LOW"),
                99,
            ),
            item.get("gap_type", ""),
            item.get("subject_id", ""),
            item.get("gap_id", ""),
        ),
    )

    tasks: list[ResearchTask] = []
    queries: list[ResearchQuery] = []

    previous_task_id: str | None = None

    for position, gap in enumerate(sorted_gaps):
        gap_id = str(gap["gap_id"])
        gap_type = str(gap["gap_type"])
        subject_id = str(gap["subject_id"])
        priority = str(gap["priority"])

        task_type = _GAP_TASK_TYPES.get(
            gap_type,
            "REVIEW_UNUSED_SOURCE",
        )

        claim = claims_by_id.get(subject_id)
        subject_text = (
            str(claim["claim_text"])
            if claim is not None
            else subject_id
        )

        assessment = assessment_by_claim.get(
            subject_id,
            {},
        )

        contradiction_records = (
            contradictions_by_claim.get(subject_id, [])
        )

        task_id = deterministic_id(
            "research_task",
            [
                project["project_id"],
                gap_id,
                task_type,
                priority,
                subject_id,
            ],
        )

        query_texts = _build_query_texts(
            task_type,
            subject_text,
            contradiction_records,
        )

        task_queries: list[ResearchQuery] = []

        for query_position, query_text in enumerate(
            query_texts
        ):
            query_id = deterministic_id(
                "research_query",
                [
                    task_id,
                    query_text,
                    query_position,
                ],
            )

            task_queries.append(
                ResearchQuery(
                    query_id=query_id,
                    task_id=task_id,
                    query_text=query_text,
                    query_strategy=_query_strategy(task_type),
                    discovery_channels=list(
                        _CHANNELS_BY_TASK[task_type]
                    ),
                    verification_requirement=(
                        _VERIFICATION_BY_TASK[task_type]
                    ),
                    position=query_position,
                )
            )

        dependencies: list[str] = []

        if (
            task_type != "REPAIR_PROVENANCE"
            and assessment.get(
                "provenance_integrity"
            ) == "INVALID"
        ):
            provenance_task = next(
                (
                    task
                    for task in tasks
                    if task.subject_id == subject_id
                    and task.task_type
                    == "REPAIR_PROVENANCE"
                ),
                None,
            )

            if provenance_task:
                dependencies.append(
                    provenance_task.task_id
                )

        if (
            priority in {"MEDIUM", "LOW"}
            and previous_task_id is not None
        ):
            dependencies.append(previous_task_id)

        dependencies = sorted(set(dependencies))

        task = ResearchTask(
            task_id=task_id,
            subject_id=subject_id,
            gap_id=gap_id,
            gap_type=gap_type,
            task_type=task_type,
            title=_task_title(
                task_type,
                subject_id,
            ),
            objective=_task_objective(
                task_type,
                subject_id,
                subject_text,
            ),
            priority=priority,
            dependency_ids=dependencies,
            completion_criteria=_completion_criteria(
                task_type
            ),
            query_ids=[
                item.query_id
                for item in task_queries
            ],
            position=position,
        )

        tasks.append(task)
        queries.extend(task_queries)
        previous_task_id = task_id

    task_ids = [item.task_id for item in tasks]
    query_ids = [item.query_id for item in queries]

    plan_id = deterministic_id(
        "research_plan",
        [
            project["project_id"],
            gaps_payload["assessment_run_id"],
            task_ids,
            query_ids,
        ],
    )

    plan = ResearchPlan(
        plan_id=plan_id,
        project_id=project["project_id"],
        assessment_run_id=(
            gaps_payload["assessment_run_id"]
        ),
        task_ids=task_ids,
        query_ids=query_ids,
        critical_task_count=sum(
            item.priority == "CRITICAL"
            for item in tasks
        ),
        task_count=len(tasks),
        query_count=len(queries),
    )

    common = {
        "schema_version": RESEARCH_PLAN_SCHEMA_VERSION,
        "project_id": project["project_id"],
        "research_plan_id": plan_id,
        "assessment_run_id": plan.assessment_run_id,
        "created_at": CANONICAL_TIMESTAMP,
    }

    plan_payload = {
        **common,
        "plan": asdict(plan),
    }

    tasks_payload = {
        **common,
        "tasks": [asdict(item) for item in tasks],
    }

    queries_payload = {
        **common,
        "queries": [asdict(item) for item in queries],
    }

    result_payload = {
        **common,
        "status": "PLANNED",
        "task_count": len(tasks),
        "query_count": len(queries),
        "critical_task_count": plan.critical_task_count,
        "high_task_count": sum(
            item.priority == "HIGH"
            for item in tasks
        ),
        "medium_task_count": sum(
            item.priority == "MEDIUM"
            for item in tasks
        ),
        "low_task_count": sum(
            item.priority == "LOW"
            for item in tasks
        ),
        "limitations": [
            "No source retrieval is performed.",
            "Queries are deterministic research briefs, not search results.",
            "Completion requires ingestion, extraction, and reassessment.",
            "Research tasks are generated only from recorded assessment gaps.",
        ],
    }

    research_root = (
        Path(paths.working_root)
        / "research"
    )
    research_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    files = {
        "research-plan.json": plan_payload,
        "research-tasks.json": tasks_payload,
        "research-queries.json": queries_payload,
        "research-result.json": result_payload,
    }

    for filename, payload in files.items():
        _write_json(
            research_root / filename,
            payload,
        )

    with SQLitePersistenceAdapter(
        SQLiteConnectionConfig(paths.database)
    ) as adapter:
        adapter.initialize()

        transaction = adapter.save_many(
            [
                (
                    "RESEARCH_PLAN",
                    plan_id,
                    plan_payload,
                ),
                (
                    "RESEARCH_TASKS",
                    plan_id,
                    tasks_payload,
                ),
                (
                    "RESEARCH_QUERIES",
                    plan_id,
                    queries_payload,
                ),
                (
                    "RESEARCH_PLAN_RESULT",
                    plan_id,
                    result_payload,
                ),
            ]
        )

    if not transaction.committed:
        raise RuntimeError(
            transaction.error_code
            or "RESEARCH_PLAN_PERSISTENCE_FAILED"
        )

    return {
        **result_payload,
        "research_root": str(research_root),
        "persistence_record_ids": (
            transaction.record_ids
        ),
    }


def _research_artifact(
    project_root: Path,
    filename: str,
) -> dict[str, Any]:
    paths = project_paths(project_root)
    path = (
        Path(paths.working_root)
        / "research"
        / filename
    )
    payload = _read_json(path)

    if (
        payload.get("schema_version")
        != RESEARCH_PLAN_SCHEMA_VERSION
    ):
        raise ValueError("INVALID_RESEARCH_PLAN_SCHEMA")

    return payload


def research_status(
    project_root: str,
) -> dict[str, Any]:
    root = _absolute_path(
        project_root,
        "PROJECT_ROOT",
    )
    project = load_project(root)
    paths = project_paths(root)

    result_path = (
        Path(paths.working_root)
        / "research"
        / "research-result.json"
    )

    if not result_path.is_file():
        return {
            "project_id": project["project_id"],
            "status": "NOT_RUN",
            "result_path": str(result_path),
        }

    payload = _read_json(result_path)

    return {
        "project_id": project["project_id"],
        "status": payload.get("status", "INVALID"),
        "result_path": str(result_path),
        "research_plan_id": payload.get(
            "research_plan_id",
            "",
        ),
        "assessment_run_id": payload.get(
            "assessment_run_id",
            "",
        ),
        "task_count": payload.get(
            "task_count",
            0,
        ),
        "query_count": payload.get(
            "query_count",
            0,
        ),
        "critical_task_count": payload.get(
            "critical_task_count",
            0,
        ),
    }


def list_research_tasks(
    project_root: str,
) -> dict[str, Any]:
    root = _absolute_path(
        project_root,
        "PROJECT_ROOT",
    )
    payload = _research_artifact(
        root,
        "research-tasks.json",
    )

    return {
        "project_id": payload["project_id"],
        "research_plan_id": payload[
            "research_plan_id"
        ],
        "task_count": len(payload["tasks"]),
        "tasks": payload["tasks"],
    }


def get_research_task(
    project_root: str,
    task_id: str,
) -> dict[str, Any]:
    root = _absolute_path(
        project_root,
        "PROJECT_ROOT",
    )

    tasks_payload = _research_artifact(
        root,
        "research-tasks.json",
    )
    queries_payload = _research_artifact(
        root,
        "research-queries.json",
    )

    task = next(
        (
            item
            for item in tasks_payload["tasks"]
            if item["task_id"] == task_id
        ),
        None,
    )

    if task is None:
        raise ValueError(
            f"RESEARCH_TASK_NOT_FOUND:{task_id}"
        )

    query_ids = set(task["query_ids"])
    queries = [
        item
        for item in queries_payload["queries"]
        if item["query_id"] in query_ids
    ]

    return {
        "project_id": tasks_payload["project_id"],
        "research_plan_id": tasks_payload[
            "research_plan_id"
        ],
        "task": task,
        "queries": queries,
    }


def verify_research_plan(
    project_root: str,
) -> ResearchPlanVerificationReport:
    root = _absolute_path(
        project_root,
        "PROJECT_ROOT",
    )
    project = load_project(root)
    issues: list[
        ResearchPlanVerificationIssue
    ] = []

    try:
        plan_payload = _research_artifact(
            root,
            "research-plan.json",
        )
        tasks_payload = _research_artifact(
            root,
            "research-tasks.json",
        )
        queries_payload = _research_artifact(
            root,
            "research-queries.json",
        )
        result_payload = _research_artifact(
            root,
            "research-result.json",
        )
        gaps_payload = _assessment_artifact(
            root,
            "research-gaps.json",
        )
    except (
        FileNotFoundError,
        ValueError,
    ) as error:
        return ResearchPlanVerificationReport(
            project_id=project["project_id"],
            status="INVALID",
            task_count=0,
            query_count=0,
            issues=[
                ResearchPlanVerificationIssue(
                    "RESEARCH_ARTIFACT_INVALID",
                    detail=str(error),
                )
            ],
        )

    plan_ids = {
        payload.get("research_plan_id")
        for payload in (
            plan_payload,
            tasks_payload,
            queries_payload,
            result_payload,
        )
    }

    if len(plan_ids) != 1:
        issues.append(
            ResearchPlanVerificationIssue(
                "RESEARCH_PLAN_ID_MISMATCH",
            )
        )

    assessment_run_ids = {
        payload.get("assessment_run_id")
        for payload in (
            plan_payload,
            tasks_payload,
            queries_payload,
            result_payload,
        )
    }

    if assessment_run_ids != {
        gaps_payload.get("assessment_run_id")
    }:
        issues.append(
            ResearchPlanVerificationIssue(
                "ASSESSMENT_RUN_ID_MISMATCH",
            )
        )

    plan = plan_payload["plan"]
    tasks = tasks_payload["tasks"]
    queries = queries_payload["queries"]

    task_ids = [
        item["task_id"]
        for item in tasks
    ]
    query_ids = [
        item["query_id"]
        for item in queries
    ]

    if len(task_ids) != len(set(task_ids)):
        issues.append(
            ResearchPlanVerificationIssue(
                "DUPLICATE_TASK_ID",
            )
        )

    if len(query_ids) != len(set(query_ids)):
        issues.append(
            ResearchPlanVerificationIssue(
                "DUPLICATE_QUERY_ID",
            )
        )

    if plan["task_ids"] != task_ids:
        issues.append(
            ResearchPlanVerificationIssue(
                "PLAN_TASK_ORDER_MISMATCH",
            )
        )

    if plan["query_ids"] != query_ids:
        issues.append(
            ResearchPlanVerificationIssue(
                "PLAN_QUERY_ORDER_MISMATCH",
            )
        )

    if [
        item["position"]
        for item in tasks
    ] != list(range(len(tasks))):
        issues.append(
            ResearchPlanVerificationIssue(
                "INVALID_TASK_POSITIONS",
            )
        )

    queries_by_task: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    for query in queries:
        queries_by_task.setdefault(
            query["task_id"],
            [],
        ).append(query)

        if (
            not query["query_text"]
            or not query["discovery_channels"]
            or not query[
                "verification_requirement"
            ]
        ):
            issues.append(
                ResearchPlanVerificationIssue(
                    "INVALID_QUERY",
                    query["query_id"],
                )
            )

    valid_task_ids = set(task_ids)

    for task in tasks:
        task_id = task["task_id"]

        if task["priority"] not in _PRIORITY_ORDER:
            issues.append(
                ResearchPlanVerificationIssue(
                    "INVALID_TASK_PRIORITY",
                    task_id,
                )
            )

        if task["status"] != "PLANNED":
            issues.append(
                ResearchPlanVerificationIssue(
                    "INVALID_TASK_STATUS",
                    task_id,
                )
            )

        if not task["completion_criteria"]:
            issues.append(
                ResearchPlanVerificationIssue(
                    "MISSING_COMPLETION_CRITERIA",
                    task_id,
                )
            )

        actual_query_ids = [
            item["query_id"]
            for item in queries_by_task.get(
                task_id,
                [],
            )
        ]

        if (
            actual_query_ids
            != task["query_ids"]
        ):
            issues.append(
                ResearchPlanVerificationIssue(
                    "TASK_QUERY_MISMATCH",
                    task_id,
                )
            )

        for dependency_id in task[
            "dependency_ids"
        ]:
            if dependency_id not in valid_task_ids:
                issues.append(
                    ResearchPlanVerificationIssue(
                        "TASK_DEPENDENCY_NOT_FOUND",
                        task_id,
                        dependency_id,
                    )
                )

            dependency = next(
                (
                    item
                    for item in tasks
                    if item["task_id"]
                    == dependency_id
                ),
                None,
            )

            if (
                dependency is not None
                and dependency["position"]
                >= task["position"]
            ):
                issues.append(
                    ResearchPlanVerificationIssue(
                        "INVALID_TASK_DEPENDENCY_ORDER",
                        task_id,
                        dependency_id,
                    )
                )

    gap_ids = {
        item["gap_id"]
        for item in gaps_payload["gaps"]
    }
    task_gap_ids = {
        item["gap_id"]
        for item in tasks
    }

    if gap_ids != task_gap_ids:
        issues.append(
            ResearchPlanVerificationIssue(
                "RESEARCH_GAP_COVERAGE_MISMATCH",
            )
        )

    expected_counts = {
        "task_count": len(tasks),
        "query_count": len(queries),
        "critical_task_count": sum(
            item["priority"] == "CRITICAL"
            for item in tasks
        ),
    }

    for key, expected in expected_counts.items():
        if result_payload.get(key) != expected:
            issues.append(
                ResearchPlanVerificationIssue(
                    "RESEARCH_RESULT_COUNT_MISMATCH",
                    key,
                    f"expected={expected}",
                )
            )

    return ResearchPlanVerificationReport(
        project_id=project["project_id"],
        status="VALID" if not issues else "INVALID",
        task_count=len(tasks),
        query_count=len(queries),
        issues=issues,
    )


__all__ = [
    "RESEARCH_PLAN_SCHEMA_VERSION",
    "ResearchPlan",
    "ResearchPlanVerificationIssue",
    "ResearchPlanVerificationReport",
    "ResearchQuery",
    "ResearchTask",
    "build_research_plan",
    "get_research_task",
    "list_research_tasks",
    "research_status",
    "verify_research_plan",
]
