"""Luna Safe Technical Repair V1.

Runs inside the consolidated production worker. It may diagnose and apply a
small, validated code repair without ending the production chain. It never
retries or alters a paid media/provider task, never edits production content,
locks, receipts, budgets, policies, approved scripts, or generated assets.

The repair budget is pre-authorized with the consolidated production run:
three Luna calls maximum, 0.05 USD each, 0.15 USD total. Every call is locked
and receipted before network activity. A repair is rolled back unless all
static and focused verification gates pass.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import traceback as traceback_module
from typing import Any, Callable, Mapping, Sequence

from src.application.luna_cinematic_prompt_director_v2 import (
    _extract_output_text,
    _parse_luna_output_payload,
    _post_once,
    _usage,
)
from src.application.openai_luna_orchestrator_v1 import (
    LUNA_MODEL,
    estimate_text_cost_usd,
)


RELEASE = "SIRAJ_LUNA_SAFE_TECHNICAL_REPAIR_V1"
SCHEMA_VERSION = "siraj-luna-safe-technical-repair-v1"

SAFE_TECHNICAL_REPAIR_TOTAL_RESERVE_USD = 0.15
SAFE_TECHNICAL_REPAIR_PER_CALL_MAX_USD = 0.05
MAX_REPAIR_CALLS_PER_PRODUCTION_RUN = 3
MAX_PROPOSALS_PER_FAILURE = 2
MAX_FILES_PER_REPAIR = 5
MAX_CHANGED_LINES_PER_REPAIR = 200
MAX_REPLACEMENTS_PER_FILE = 8
MAX_CONTEXT_CHARACTERS = 60000
VERIFY_TIMEOUT_SECONDS = 600
MINIMUM_CONFIDENCE = 0.92

AUTHORIZATION_REL = Path(
    "projects/episode-001-adam/evidence/"
    "luna-safe-technical-repair-authorization-v1.json"
)
REPAIR_ROOT_REL = Path(
    "projects/episode-001-adam/orchestration/"
    "luna-safe-technical-repair-v1"
)

ALLOWED_ROOTS = (
    Path("src/application"),
    Path("src/presentation/desktop"),
    Path("scripts/desktop"),
    Path("scripts/fast_track"),
    Path("tests"),
)
PROTECTED_EXACT = {
    Path("src/application/luna_safe_technical_repair_v1.py"),
    Path("src/application/consolidated_episode_production_controller_v2.py"),
    Path("src/application/luna_cinematic_prompt_director_v2.py"),
    Path("src/application/luna_invalid_output_recovery_v2.py"),
}
PROTECTED_PARTS = {
    ".git",
    ".venv",
    "projects",
    "secrets",
    "credentials",
    "locks",
    "receipts",
    "generated",
    "masters",
    "approved",
}

USER_ACTION_PATTERNS = (
    "API_KEY_REQUIRED",
    "AUTHORIZATION_REQUIRED",
    "AUTHORIZATION_MAXIMUM_MISMATCH",
    "MAXIMUM_MISMATCH",
    "EXCEEDS_HARD_CAP",
    "INSUFFICIENT",
    "PAYMENT",
    "CREDIT",
    "QUOTA",
    "RATE_LIMIT",
    "NETWORK_OR_PROVIDER_RESULT_UNKNOWN",
    "NO_AUTOMATIC_RETRY",
    "ALREADY_LOCKED",
    "MANUAL_REVIEW_REQUIRED",
    "HUMAN_FINAL_REVIEW_REQUIRED",
    "HUMAN_SCOPE_REVIEW_REQUIRED",
    "PROVIDER_REJECTION",
    "TERMINAL_REJECTION",
    "REFUSAL",
    "LUNA_RESPONSE_INCOMPLETE",
    "INVALID_LUNA_OUTPUT",
    "PAID_MEDIA_AUTHORIZATION_REQUIRED",
    "PERMISSIONERROR",
    "ACCESS_DENIED",
)
REPAIRABLE_PATTERNS = (
    "SYNTAXERROR",
    "IMPORTERROR",
    "MODULENOTFOUNDERROR",
    "KEYERROR",
    "ATTRIBUTEERROR",
    "TYPEERROR",
    "NAMEERROR",
    "UNBOUNDLOCALERROR",
    "JSONDECODEERROR",
    "UNICODEDECODEERROR",
    "UNICODEENCODEERROR",
    "VALUEERROR",
    "ASSERTIONERROR",
    "FFMPEG",
    "PYSIDE",
    "QT",
    "COMPILE",
    "PYTEST",
    "UNMATCHED",
    "UNEXPECTED CHARACTER",
    "NO SUCH FILE OR DIRECTORY",
)
FORBIDDEN_CHANGE_TOKENS = (
    "HARD_CAP",
    "QUALITY_THRESHOLD",
    "MAXIMUM_AUTHORIZED_USD",
    "automatic_paid_retry",
    "hidden_paid_retry",
    "VOICE_ID",
    "LUNA_MODEL",
    "OPENAI_RESPONSES_URL",
    "FORBIDDEN_DIRECT_DEPICTION",
    "SERIES_STANDARD",
    "DIRECTOR_BIBLE",
)
DANGEROUS_NEW_TOKENS = (
    "git reset",
    "git clean",
    "git checkout",
    "git switch",
    "git push",
    "os.system(",
    "eval(",
    "exec(",
    "pickle.loads(",
    "yaml.load(",
    "shutil.rmtree(",
)

ProgressCallback = Callable[[str, int | None], None]


class SafeTechnicalRepairError(RuntimeError):
    pass


class SafeTechnicalRepairUserActionRequired(SafeTechnicalRepairError):
    pass


class SafeTechnicalRepairProposalRejected(SafeTechnicalRepairError):
    pass


@dataclass(frozen=True, slots=True)
class SafeRepairResult:
    status: str
    repair_id: str
    fingerprint: str
    changed_paths: tuple[str, ...]
    changed_lines: int
    proposal_index: int
    response_id: str
    estimated_cost_usd: float
    verification_summary: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SafeTechnicalRepairError(
            f"CANNOT_READ_JSON:{path}:{exc}"
        ) from exc
    if not isinstance(value, dict):
        raise SafeTechnicalRepairError(
            f"JSON_OBJECT_REQUIRED:{path}"
        )
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _emit(
    progress: ProgressCallback | None,
    message: str,
    value: int | None = None,
) -> None:
    if progress is not None:
        progress(message, value)


def create_safe_repair_authorization(
    repo_root: Path,
    *,
    confirmed_reserve_usd: float,
    effective_consolidated_maximum_usd: float,
    episode_hard_cap_usd: float,
) -> Path:
    if abs(
        float(confirmed_reserve_usd)
        - SAFE_TECHNICAL_REPAIR_TOTAL_RESERVE_USD
    ) > 1e-9:
        raise SafeTechnicalRepairError(
            "SAFE_REPAIR_RESERVE_AUTHORIZATION_MISMATCH"
        )
    if (
        float(effective_consolidated_maximum_usd)
        > float(episode_hard_cap_usd) + 1e-9
    ):
        raise SafeTechnicalRepairError(
            "SAFE_REPAIR_EFFECTIVE_MAXIMUM_EXCEEDS_HARD_CAP"
        )

    repo = repo_root.resolve()
    path = repo / AUTHORIZATION_REL
    if path.is_file():
        current = _read(path)
        if (
            str(current.get("status") or "") in {"ACTIVE", "COMPLETE"}
            and abs(
                float(current.get("maximum_authorized_usd", 0.0))
                - SAFE_TECHNICAL_REPAIR_TOTAL_RESERVE_USD
            )
            <= 1e-9
        ):
            return path
        raise SafeTechnicalRepairError(
            "SAFE_REPAIR_AUTHORIZATION_CONFLICT"
        )

    _write(
        path,
        {
            "schema_version": (
                "siraj-luna-safe-technical-repair-authorization-v1"
            ),
            "release": RELEASE,
            "status": "ACTIVE",
            "decision": (
                "AUTHORIZED_AUTOMATIC_BOUNDED_TECHNICAL_REPAIR_"
                "DURING_PRODUCTION"
            ),
            "maximum_authorized_usd": (
                SAFE_TECHNICAL_REPAIR_TOTAL_RESERVE_USD
            ),
            "maximum_provider_calls": (
                MAX_REPAIR_CALLS_PER_PRODUCTION_RUN
            ),
            "maximum_per_call_usd": (
                SAFE_TECHNICAL_REPAIR_PER_CALL_MAX_USD
            ),
            "calls_consumed": 0,
            "estimated_cost_consumed_usd": 0.0,
            "effective_consolidated_maximum_usd": (
                effective_consolidated_maximum_usd
            ),
            "episode_hard_cap_usd": episode_hard_cap_usd,
            "automatic_media_retry": "FORBIDDEN",
            "automatic_provider_task_retry": "FORBIDDEN",
            "architectural_changes": "FORBIDDEN",
            "git_commit": "FORBIDDEN_DURING_PRODUCTION",
            "git_push": "FORBIDDEN_DURING_PRODUCTION",
            "authorization_source": (
                "CONSOLIDATED_DESKTOP_CONFIRMATION"
            ),
            "authorized_at_utc": _now(),
        },
    )
    return path


def _consume_repair_call_before_network(
    repo: Path,
    *,
    repair_id: str,
    fingerprint: str,
) -> tuple[Path, int]:
    path = repo / AUTHORIZATION_REL
    if not path.is_file():
        raise SafeTechnicalRepairUserActionRequired(
            "USER_ACTION_REQUIRED:SAFE_REPAIR_AUTHORIZATION_MISSING"
        )
    authorization = _read(path)
    if str(authorization.get("status") or "") != "ACTIVE":
        raise SafeTechnicalRepairUserActionRequired(
            "USER_ACTION_REQUIRED:SAFE_REPAIR_AUTHORIZATION_NOT_ACTIVE"
        )
    consumed = int(authorization.get("calls_consumed", 0) or 0)
    maximum = int(
        authorization.get(
            "maximum_provider_calls",
            MAX_REPAIR_CALLS_PER_PRODUCTION_RUN,
        )
        or 0
    )
    if consumed >= maximum:
        raise SafeTechnicalRepairUserActionRequired(
            "USER_ACTION_REQUIRED:SAFE_REPAIR_CALL_LIMIT_EXHAUSTED"
        )
    consumed += 1
    authorization["calls_consumed"] = consumed
    authorization["last_repair_id"] = repair_id
    authorization["last_fingerprint"] = fingerprint
    authorization["last_call_consumed_at_utc"] = _now()
    _write(path, authorization)
    return path, consumed


def _record_cost(
    authorization_path: Path,
    estimated_cost_usd: float,
) -> None:
    authorization = _read(authorization_path)
    total = round(
        float(
            authorization.get(
                "estimated_cost_consumed_usd",
                0.0,
            )
            or 0.0
        )
        + float(estimated_cost_usd),
        8,
    )
    if total > (
        SAFE_TECHNICAL_REPAIR_TOTAL_RESERVE_USD + 1e-9
    ):
        authorization["status"] = "COST_RESERVE_EXCEEDED"
        authorization["estimated_cost_consumed_usd"] = total
        _write(authorization_path, authorization)
        raise SafeTechnicalRepairUserActionRequired(
            "USER_ACTION_REQUIRED:SAFE_REPAIR_COST_RESERVE_EXCEEDED"
        )
    authorization["estimated_cost_consumed_usd"] = total
    authorization["updated_at_utc"] = _now()
    _write(authorization_path, authorization)


def _classify_without_provider(
    error: str,
    traceback_text: str,
) -> str:
    combined = (error + "\n" + traceback_text).upper()
    if any(pattern in combined for pattern in USER_ACTION_PATTERNS):
        return "USER_ACTION_REQUIRED"
    if any(pattern in combined for pattern in REPAIRABLE_PATTERNS):
        return "SAFE_REPAIR_CANDIDATE"
    return "USER_ACTION_REQUIRED"


def _repo_relative_path(repo: Path, value: str) -> Path | None:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = repo / candidate
    try:
        resolved = candidate.resolve()
        relative = resolved.relative_to(repo)
    except (OSError, ValueError):
        return None
    return relative


def _traceback_frames(
    repo: Path,
    traceback_text: str,
) -> list[tuple[Path, int]]:
    result: list[tuple[Path, int]] = []
    pattern = re.compile(
        r'File\s+["\'](?P<path>[^"\']+\.py)["\'],\s+line\s+(?P<line>\d+)'
    )
    for match in pattern.finditer(traceback_text):
        relative = _repo_relative_path(
            repo,
            match.group("path"),
        )
        if relative is None:
            continue
        item = (relative, int(match.group("line")))
        if item not in result:
            result.append(item)
    return result[-8:]


def _is_allowed_path(relative: Path) -> bool:
    if relative in PROTECTED_EXACT:
        return False
    if any(part.lower() in PROTECTED_PARTS for part in relative.parts):
        return False
    return any(
        relative == root or root in relative.parents
        for root in ALLOWED_ROOTS
    )


def _read_snippet(
    path: Path,
    line_number: int,
    radius: int = 90,
) -> str:
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    start = max(0, line_number - radius - 1)
    end = min(len(lines), line_number + radius)
    return "\n".join(
        f"{index + 1:05d}: {lines[index]}"
        for index in range(start, end)
    )


def _git_status_for_path(repo: Path, relative: Path) -> str:
    process = subprocess.run(
        ["git", "status", "--porcelain", "--", str(relative)],
        cwd=str(repo),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    return process.stdout.strip()


def _collect_context(
    repo: Path,
    *,
    error: str,
    traceback_text: str,
    stage: str,
    previous_feedback: str,
) -> tuple[str, tuple[Path, ...]]:
    frames = _traceback_frames(repo, traceback_text)
    allowed_frames = [
        (relative, line)
        for relative, line in frames
        if _is_allowed_path(relative)
        and (repo / relative).is_file()
    ]
    if not allowed_frames:
        raise SafeTechnicalRepairUserActionRequired(
            "USER_ACTION_REQUIRED:NO_ALLOWED_REPOSITORY_FRAME_FOR_SAFE_REPAIR"
        )

    sections = [
        "SIRAJ LUNA SAFE TECHNICAL REPAIR V1",
        f"STAGE: {stage}",
        "ERROR:",
        error,
        "TRACEBACK:",
        traceback_text[-16000:],
    ]
    if previous_feedback:
        sections.extend(
            ["PREVIOUS_REJECTED_PROPOSAL_FEEDBACK:", previous_feedback]
        )

    paths: list[Path] = []
    for relative, line in allowed_frames:
        if relative in paths:
            continue
        paths.append(relative)
        sections.extend(
            [
                f"FILE: {relative.as_posix()} LINE: {line}",
                f"GIT_STATUS: {_git_status_for_path(repo, relative) or 'CLEAN'}",
                _read_snippet(repo / relative, line),
            ]
        )

    context = "\n\n".join(sections)
    if len(context) > MAX_CONTEXT_CHARACTERS:
        context = context[:MAX_CONTEXT_CHARACTERS]
    return context, tuple(paths)


def _repair_schema() -> dict[str, Any]:
    replacement = {
        "type": "object",
        "additionalProperties": False,
        "required": ["old", "new", "expected_count"],
        "properties": {
            "old": {"type": "string", "minLength": 1},
            "new": {"type": "string"},
            "expected_count": {
                "type": "integer",
                "enum": [1],
            },
        },
    }
    edit = {
        "type": "object",
        "additionalProperties": False,
        "required": ["path", "reason", "replacements"],
        "properties": {
            "path": {"type": "string", "minLength": 1},
            "reason": {"type": "string", "minLength": 1},
            "replacements": {
                "type": "array",
                "maxItems": MAX_REPLACEMENTS_PER_FILE,
                "items": replacement,
            },
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "decision",
            "confidence",
            "root_cause",
            "user_action_ar",
            "edits",
            "tests",
        ],
        "properties": {
            "decision": {
                "type": "string",
                "enum": [
                    "APPLY_SAFE_REPAIR",
                    "USER_ACTION_REQUIRED",
                    "NO_REPAIR",
                ],
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
            },
            "root_cause": {"type": "string"},
            "user_action_ar": {"type": "string"},
            "edits": {
                "type": "array",
                "maxItems": MAX_FILES_PER_REPAIR,
                "items": edit,
            },
            "tests": {
                "type": "array",
                "maxItems": 8,
                "items": {"type": "string"},
            },
        },
    }


def _build_request(context: str) -> dict[str, Any]:
    developer = (
        "You are Luna acting as a bounded technical repair engineer for SIRAJ. "
        "Return only the strict JSON object. Diagnose the concrete traceback and "
        "propose the smallest exact-substring repair. You may edit only existing "
        "files shown in context. Never change architecture, public schemas, "
        "budgets, model/provider choices, production policies, quality thresholds, "
        "religious constraints, approved content, locks, receipts, generated media, "
        "credentials, dependencies, or Git history. Never delete files. Never add "
        "network calls, subprocess Git operations, automatic paid retries, or test "
        "bypasses. Choose USER_ACTION_REQUIRED whenever provider state, money, API "
        "keys, permissions, human review, ambiguous locks, or architectural work is "
        "involved. APPLY_SAFE_REPAIR only with confidence at least 0.92 and exact "
        "old/new replacements that preserve behavior outside the root cause."
    )
    return {
        "model": LUNA_MODEL,
        "input": [
            {
                "role": "developer",
                "content": [
                    {"type": "input_text", "text": developer}
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": context}
                ],
            },
        ],
        "reasoning": {"effort": "medium"},
        "max_output_tokens": 12000,
        "text": {
            "verbosity": "low",
            "format": {
                "type": "json_schema",
                "name": "siraj_safe_technical_repair_v1",
                "strict": True,
                "schema": _repair_schema(),
            },
        },
    }


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return value
    return ()


def _normalize_test_paths(
    repo: Path,
    requested: Sequence[Any],
    changed_paths: Sequence[Path],
) -> tuple[str, ...]:
    candidates: list[str] = []
    for value in requested:
        item = str(value).strip().replace("\\", "/")
        if not item.startswith("tests/") or not item.endswith(".py"):
            continue
        if (repo / item).is_file() and item not in candidates:
            candidates.append(item)

    for path in changed_paths:
        if path.parts[:2] == ("src", "application"):
            expected = "tests/test_" + path.stem + ".py"
            if (repo / expected).is_file() and expected not in candidates:
                candidates.append(expected)

    return tuple(candidates[:6])


def _validate_and_prepare_edits(
    repo: Path,
    payload: Mapping[str, Any],
    *,
    context_paths: Sequence[Path],
    owned_modified_paths: set[Path],
) -> tuple[dict[Path, str], int, tuple[str, ...]]:
    decision = str(payload.get("decision") or "")
    if decision != "APPLY_SAFE_REPAIR":
        action = str(payload.get("user_action_ar") or "")
        raise SafeTechnicalRepairUserActionRequired(
            "USER_ACTION_REQUIRED:"
            + (action or decision or "LUNA_DECLINED_SAFE_REPAIR")
        )
    confidence = float(payload.get("confidence", 0.0) or 0.0)
    if confidence < MINIMUM_CONFIDENCE:
        raise SafeTechnicalRepairProposalRejected(
            f"REPAIR_CONFIDENCE_TOO_LOW:{confidence:.3f}"
        )

    edits = [
        item
        for item in _sequence(payload.get("edits"))
        if isinstance(item, Mapping)
    ]
    if not edits or len(edits) > MAX_FILES_PER_REPAIR:
        raise SafeTechnicalRepairProposalRejected(
            "SAFE_REPAIR_EDIT_COUNT_INVALID"
        )

    allowed_context = set(context_paths)
    prepared: dict[Path, str] = {}
    total_changed_lines = 0

    for edit in edits:
        relative = Path(str(edit.get("path") or "").replace("\\", "/"))
        if relative.is_absolute() or not _is_allowed_path(relative):
            raise SafeTechnicalRepairProposalRejected(
                f"SAFE_REPAIR_PATH_FORBIDDEN:{relative}"
            )
        if relative not in allowed_context:
            raise SafeTechnicalRepairProposalRejected(
                f"SAFE_REPAIR_PATH_NOT_IN_TRACEBACK_CONTEXT:{relative}"
            )
        path = (repo / relative).resolve()
        try:
            path.relative_to(repo)
        except ValueError as exc:
            raise SafeTechnicalRepairProposalRejected(
                f"SAFE_REPAIR_PATH_ESCAPES_REPOSITORY:{relative}"
            ) from exc
        if not path.is_file() or path.is_symlink():
            raise SafeTechnicalRepairProposalRejected(
                f"SAFE_REPAIR_EXISTING_REGULAR_FILE_REQUIRED:{relative}"
            )
        dirty = _git_status_for_path(repo, relative)
        if dirty and relative not in owned_modified_paths:
            raise SafeTechnicalRepairUserActionRequired(
                f"USER_ACTION_REQUIRED:CODE_FILE_ALREADY_MODIFIED:{relative}"
            )

        original = path.read_text(encoding="utf-8-sig")
        revised = original
        replacements = [
            item
            for item in _sequence(edit.get("replacements"))
            if isinstance(item, Mapping)
        ]
        if not replacements or len(replacements) > MAX_REPLACEMENTS_PER_FILE:
            raise SafeTechnicalRepairProposalRejected(
                f"SAFE_REPAIR_REPLACEMENT_COUNT_INVALID:{relative}"
            )

        for replacement in replacements:
            old = str(replacement.get("old") or "")
            new = str(replacement.get("new") or "")
            if not old or old == new:
                raise SafeTechnicalRepairProposalRejected(
                    f"SAFE_REPAIR_EMPTY_OR_NOOP_REPLACEMENT:{relative}"
                )
            if int(replacement.get("expected_count", 0) or 0) != 1:
                raise SafeTechnicalRepairProposalRejected(
                    f"SAFE_REPAIR_EXPECTED_COUNT_MUST_BE_ONE:{relative}"
                )
            if revised.count(old) != 1:
                raise SafeTechnicalRepairProposalRejected(
                    f"SAFE_REPAIR_EXACT_MATCH_COUNT_INVALID:{relative}"
                )
            combined = old + "\n" + new
            if any(token in combined for token in FORBIDDEN_CHANGE_TOKENS):
                raise SafeTechnicalRepairProposalRejected(
                    f"SAFE_REPAIR_PROTECTED_INVARIANT_TOUCHED:{relative}"
                )
            lowered_old = old.lower()
            lowered_new = new.lower()
            for token in DANGEROUS_NEW_TOKENS:
                if lowered_new.count(token.lower()) > lowered_old.count(
                    token.lower()
                ):
                    raise SafeTechnicalRepairProposalRejected(
                        f"SAFE_REPAIR_DANGEROUS_CAPABILITY_ADDED:{relative}:{token}"
                    )
            if relative.parts and relative.parts[0] == "tests":
                if new.count("assert") < old.count("assert"):
                    raise SafeTechnicalRepairProposalRejected(
                        f"SAFE_REPAIR_TEST_ASSERTION_WEAKENED:{relative}"
                    )
                if new.count("pytest.raises") < old.count("pytest.raises"):
                    raise SafeTechnicalRepairProposalRejected(
                        f"SAFE_REPAIR_TEST_EXCEPTION_GATE_WEAKENED:{relative}"
                    )
            total_changed_lines += max(
                len(old.splitlines()),
                len(new.splitlines()),
            )
            revised = revised.replace(old, new, 1)

        if revised == original:
            raise SafeTechnicalRepairProposalRejected(
                f"SAFE_REPAIR_FILE_UNCHANGED:{relative}"
            )
        if relative.suffix == ".py":
            try:
                compile(revised, str(relative), "exec")
            except SyntaxError as exc:
                raise SafeTechnicalRepairProposalRejected(
                    f"SAFE_REPAIR_PRODUCES_SYNTAX_ERROR:{relative}:{exc}"
                ) from exc
        prepared[relative] = revised

    if total_changed_lines > MAX_CHANGED_LINES_PER_REPAIR:
        raise SafeTechnicalRepairProposalRejected(
            f"SAFE_REPAIR_CHANGED_LINE_LIMIT_EXCEEDED:{total_changed_lines}"
        )

    tests = _normalize_test_paths(
        repo,
        _sequence(payload.get("tests")),
        tuple(prepared),
    )
    return prepared, total_changed_lines, tests


def _backup_and_apply(
    repo: Path,
    repair_id: str,
    prepared: Mapping[Path, str],
) -> Path:
    backup_root = repo / REPAIR_ROOT_REL / "backups" / repair_id
    manifest: dict[str, Any] = {
        "schema_version": "siraj-safe-repair-backup-v1",
        "repair_id": repair_id,
        "created_at_utc": _now(),
        "files": [],
    }
    for relative, revised in prepared.items():
        source = repo / relative
        original_bytes = source.read_bytes()
        backup = backup_root / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(original_bytes)
        manifest["files"].append(
            {
                "path": relative.as_posix(),
                "sha256_before": hashlib.sha256(original_bytes).hexdigest(),
            }
        )
        temporary = source.with_suffix(source.suffix + ".safe-repair.tmp")
        temporary.write_text(
            revised.rstrip("\r\n") + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary, source)
    _write(backup_root / "manifest.json", manifest)
    return backup_root


def _rollback(
    repo: Path,
    backup_root: Path,
) -> None:
    manifest = _read(backup_root / "manifest.json")
    for item in _sequence(manifest.get("files")):
        if not isinstance(item, Mapping):
            continue
        relative = Path(str(item.get("path") or ""))
        backup = backup_root / relative
        destination = repo / relative
        if backup.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(
                destination.suffix + ".rollback.tmp"
            )
            temporary.write_bytes(backup.read_bytes())
            os.replace(temporary, destination)


def _run_command(
    repo: Path,
    args: Sequence[str],
    *,
    timeout: int = VERIFY_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    environment["QT_QPA_PLATFORM"] = "offscreen"
    try:
        process = subprocess.run(
            [str(value) for value in args],
            cwd=str(repo),
            env=environment,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise SafeTechnicalRepairProposalRejected(
            "SAFE_REPAIR_VERIFICATION_TIMEOUT"
        ) from exc
    if process.returncode != 0:
        raise SafeTechnicalRepairProposalRejected(
            "SAFE_REPAIR_VERIFICATION_FAILED:"
            + " ".join(str(value) for value in args)
            + "\nSTDOUT:\n"
            + process.stdout[-6000:]
            + "\nSTDERR:\n"
            + process.stderr[-6000:]
        )
    return process


def _verify_repair(
    repo: Path,
    changed_paths: Sequence[Path],
    tests: Sequence[str],
) -> str:
    python_files = [
        str(path)
        for path in changed_paths
        if path.suffix == ".py"
    ]
    if python_files:
        _run_command(
            repo,
            [
                sys.executable,
                "-X",
                "utf8",
                "-m",
                "py_compile",
                *python_files,
            ],
        )
    _run_command(
        repo,
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "compileall",
            "-q",
            "src/application",
            "src/presentation/desktop",
            "scripts/desktop",
            "scripts/fast_track",
        ],
    )
    if tests:
        _run_command(
            repo,
            [
                sys.executable,
                "-X",
                "utf8",
                "-m",
                "pytest",
                "-q",
                *tests,
            ],
        )
    _run_command(
        repo,
        [
            "git",
            "-c",
            "core.safecrlf=false",
            "diff",
            "--check",
        ],
    )
    return (
        "py_compile=PASS;compileall=PASS;"
        + ("pytest=PASS;" if tests else "pytest=NOT_APPLICABLE;")
        + "git_diff_check=PASS"
    )


def _reload_changed_modules(
    repo: Path,
    changed_paths: Sequence[Path],
) -> None:
    importlib.invalidate_caches()
    module_names: list[str] = []
    for relative in changed_paths:
        if relative.suffix != ".py":
            continue
        if relative.name == "__init__.py":
            parts = relative.parent.parts
        else:
            parts = relative.with_suffix("").parts
        module_name = ".".join(parts)
        if module_name in sys.modules:
            module_names.append(module_name)
    for module_name in module_names:
        importlib.reload(sys.modules[module_name])
    for module_name in (
        "src.application.end_to_end_production_v1",
        "src.application.consolidated_episode_production_controller_v2",
    ):
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])


def _request_repair_proposal(
    repo: Path,
    *,
    api_key: str,
    context: str,
    fingerprint: str,
    proposal_index: int,
) -> tuple[dict[str, Any], str, float, str]:
    repair_id = (
        "REPAIR-"
        + fingerprint[:12].upper()
        + f"-P{proposal_index:02d}"
    )
    root = repo / REPAIR_ROOT_REL
    lock_path = root / "locks" / f"{repair_id}.json"
    raw_path = root / "raw-responses" / f"{repair_id}.json"
    receipt_path = root / "receipts" / f"{repair_id}.json"
    if lock_path.exists():
        raise SafeTechnicalRepairUserActionRequired(
            f"USER_ACTION_REQUIRED:SAFE_REPAIR_ATTEMPT_ALREADY_LOCKED:{repair_id}"
        )

    request_payload = _build_request(context)
    authorization_path, call_index = _consume_repair_call_before_network(
        repo,
        repair_id=repair_id,
        fingerprint=fingerprint,
    )
    lock = {
        "schema_version": "siraj-safe-repair-call-lock-v1",
        "release": RELEASE,
        "repair_id": repair_id,
        "fingerprint": fingerprint,
        "proposal_index": proposal_index,
        "call_index": call_index,
        "status": "LOCKED_BEFORE_NETWORK",
        "maximum_provider_requests": 1,
        "provider_requests_made": 0,
        "maximum_authorized_usd": (
            SAFE_TECHNICAL_REPAIR_PER_CALL_MAX_USD
        ),
        "automatic_retry": "FORBIDDEN",
        "hidden_retry": "FORBIDDEN",
        "request_sha256": _sha256_text(
            json.dumps(
                request_payload,
                ensure_ascii=False,
                sort_keys=True,
            )
        ),
        "created_at_utc": _now(),
    }
    _write(lock_path, lock)
    lock["status"] = "NETWORK_REQUEST_STARTED"
    lock["provider_requests_made"] = 1
    lock["network_started_at_utc"] = _now()
    _write(lock_path, lock)

    try:
        response = _post_once(api_key, request_payload)
    except Exception as exc:
        lock["status"] = (
            "NETWORK_OR_PROVIDER_RESULT_UNKNOWN_USER_ACTION_REQUIRED"
        )
        lock["last_error"] = str(exc)
        lock["updated_at_utc"] = _now()
        _write(lock_path, lock)
        raise SafeTechnicalRepairUserActionRequired(
            "USER_ACTION_REQUIRED:SAFE_REPAIR_PROVIDER_RESULT_UNKNOWN:"
            + str(exc)
        ) from exc

    _write(raw_path, response)
    status = str(response.get("status") or "")
    lock["response_id"] = str(response.get("id") or "")
    lock["provider_response_status"] = status
    lock["raw_response_path"] = str(raw_path)
    _write(lock_path, lock)
    if status not in {"", "completed"}:
        lock["status"] = (
            "INCOMPLETE_OR_FAILED_USER_ACTION_REQUIRED"
        )
        lock["incomplete_details"] = response.get(
            "incomplete_details"
        )
        lock["provider_error"] = response.get("error")
        _write(lock_path, lock)
        raise SafeTechnicalRepairUserActionRequired(
            "USER_ACTION_REQUIRED:SAFE_REPAIR_RESPONSE_"
            + status.upper()
        )

    try:
        output_text = _extract_output_text(response)
        payload = _parse_luna_output_payload(output_text)
    except Exception as exc:
        lock["status"] = "INVALID_OUTPUT_USER_ACTION_REQUIRED"
        lock["last_error"] = str(exc)
        _write(lock_path, lock)
        raise SafeTechnicalRepairUserActionRequired(
            "USER_ACTION_REQUIRED:SAFE_REPAIR_OUTPUT_INVALID:"
            + str(exc)
        ) from exc

    input_tokens, output_tokens, cached_tokens = _usage(response)
    estimated_cost = estimate_text_cost_usd(
        input_tokens,
        output_tokens,
        cached_tokens,
    )
    if estimated_cost > (
        SAFE_TECHNICAL_REPAIR_PER_CALL_MAX_USD + 1e-9
    ):
        lock["status"] = "PER_CALL_COST_EXCEEDED"
        lock["estimated_cost_usd"] = estimated_cost
        _write(lock_path, lock)
        _record_cost(authorization_path, estimated_cost)
        raise SafeTechnicalRepairUserActionRequired(
            "USER_ACTION_REQUIRED:SAFE_REPAIR_PER_CALL_COST_EXCEEDED"
        )
    _record_cost(authorization_path, estimated_cost)

    receipt = {
        "schema_version": "siraj-safe-repair-call-receipt-v1",
        "release": RELEASE,
        "repair_id": repair_id,
        "fingerprint": fingerprint,
        "proposal_index": proposal_index,
        "status": "COMPLETE",
        "response_id": str(response.get("id") or ""),
        "provider_requests": 1,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_input_tokens": cached_tokens,
        "estimated_cost_usd": round(estimated_cost, 8),
        "maximum_authorized_usd": (
            SAFE_TECHNICAL_REPAIR_PER_CALL_MAX_USD
        ),
        "payload": payload,
        "completed_at_utc": _now(),
    }
    _write(receipt_path, receipt)
    lock["status"] = "COMPLETE"
    lock["receipt_path"] = str(receipt_path)
    lock["completed_at_utc"] = _now()
    _write(lock_path, lock)
    return (
        payload,
        str(response.get("id") or ""),
        float(estimated_cost),
        repair_id,
    )


def repair_failure_automatically(
    repo_root: Path,
    *,
    api_key: str,
    error: str,
    traceback_text: str,
    stage: str,
    progress: ProgressCallback | None,
    owned_modified_paths: set[Path],
) -> SafeRepairResult:
    repo = repo_root.resolve()
    classification = _classify_without_provider(
        error,
        traceback_text,
    )
    if classification != "SAFE_REPAIR_CANDIDATE":
        raise SafeTechnicalRepairUserActionRequired(
            "USER_ACTION_REQUIRED:"
            + error
        )
    if not api_key.strip():
        raise SafeTechnicalRepairUserActionRequired(
            "USER_ACTION_REQUIRED:OPENAI_API_KEY_REQUIRED_FOR_SAFE_REPAIR"
        )

    fingerprint = _sha256_text(
        stage + "\n" + error + "\n" + traceback_text
    )
    feedback = ""
    last_rejection = ""
    for proposal_index in range(1, MAX_PROPOSALS_PER_FAILURE + 1):
        _emit(
            progress,
            "لونا يشخّص العطل التقني ضمن حدود الإصلاح المقيد "
            f"({proposal_index}/{MAX_PROPOSALS_PER_FAILURE}).",
            None,
        )
        context, context_paths = _collect_context(
            repo,
            error=error,
            traceback_text=traceback_text,
            stage=stage,
            previous_feedback=feedback,
        )
        payload, response_id, estimated_cost, repair_id = (
            _request_repair_proposal(
                repo,
                api_key=api_key,
                context=context,
                fingerprint=fingerprint,
                proposal_index=proposal_index,
            )
        )
        try:
            prepared, changed_lines, tests = (
                _validate_and_prepare_edits(
                    repo,
                    payload,
                    context_paths=context_paths,
                    owned_modified_paths=owned_modified_paths,
                )
            )
            backup_root = _backup_and_apply(
                repo,
                repair_id,
                prepared,
            )
            try:
                verification = _verify_repair(
                    repo,
                    tuple(prepared),
                    tests,
                )
            except Exception:
                _rollback(repo, backup_root)
                raise
        except SafeTechnicalRepairUserActionRequired:
            raise
        except Exception as exc:
            last_rejection = str(exc)
            feedback = (
                "The prior proposal was rejected or rolled back by the "
                "deterministic gate: "
                + last_rejection
                + ". Produce a smaller different repair, or choose "
                "USER_ACTION_REQUIRED."
            )
            _write(
                repo
                / REPAIR_ROOT_REL
                / "rejections"
                / f"{repair_id}.json",
                {
                    "schema_version": (
                        "siraj-safe-repair-proposal-rejection-v1"
                    ),
                    "repair_id": repair_id,
                    "fingerprint": fingerprint,
                    "reason": last_rejection,
                    "rolled_back": True,
                    "rejected_at_utc": _now(),
                },
            )
            continue

        changed_paths = tuple(path.as_posix() for path in prepared)
        owned_modified_paths.update(prepared)
        _reload_changed_modules(repo, tuple(prepared))
        result = SafeRepairResult(
            status="PASS_SAFE_TECHNICAL_REPAIR",
            repair_id=repair_id,
            fingerprint=fingerprint,
            changed_paths=changed_paths,
            changed_lines=changed_lines,
            proposal_index=proposal_index,
            response_id=response_id,
            estimated_cost_usd=round(estimated_cost, 8),
            verification_summary=verification,
        )
        _write(
            repo / REPAIR_ROOT_REL / "reports" / f"{repair_id}.json",
            {
                "schema_version": SCHEMA_VERSION,
                "release": RELEASE,
                **result.as_dict(),
                "root_cause": str(payload.get("root_cause") or ""),
                "architecture_changed": False,
                "production_policy_changed": False,
                "budget_changed": False,
                "provider_task_retried": False,
                "rollback_available": True,
                "completed_at_utc": _now(),
            },
        )
        _emit(
            progress,
            "نجح الإصلاح التقني المقيد. يستأنف سراج سلسلة الإنتاج تلقائيًا.",
            None,
        )
        return result

    raise SafeTechnicalRepairUserActionRequired(
        "USER_ACTION_REQUIRED:SAFE_REPAIR_PROPOSALS_REJECTED:"
        + last_rejection
    )


def run_consolidated_production_with_safe_technical_repair(
    repo_root: Path,
    *,
    openai_api_key: str,
    runware_api_key: str,
    elevenlabs_api_key: str,
    confirmed_maximum_usd: float,
    progress: ProgressCallback | None = None,
):
    repo = repo_root.resolve()
    create_safe_repair_authorization(
        repo,
        confirmed_reserve_usd=(
            SAFE_TECHNICAL_REPAIR_TOTAL_RESERVE_USD
        ),
        effective_consolidated_maximum_usd=(
            confirmed_maximum_usd
        ),
        episode_hard_cap_usd=40.0,
    )
    owned_modified_paths: set[Path] = set()
    repairs_completed = 0

    while True:
        try:
            from src.application import (
                consolidated_episode_production_controller_v2
                as controller,
            )
            return controller.run_consolidated_production_to_human_gate(
                repo,
                openai_api_key=openai_api_key,
                runware_api_key=runware_api_key,
                elevenlabs_api_key=elevenlabs_api_key,
                confirmed_maximum_usd=confirmed_maximum_usd,
                progress=progress,
            )
        except SafeTechnicalRepairUserActionRequired:
            raise
        except Exception as exc:
            error = str(exc)
            traceback_text = traceback_module.format_exc()
            if repairs_completed >= MAX_REPAIR_CALLS_PER_PRODUCTION_RUN:
                raise SafeTechnicalRepairUserActionRequired(
                    "USER_ACTION_REQUIRED:SAFE_REPAIR_LIMIT_REACHED:"
                    + error
                ) from exc
            try:
                result = repair_failure_automatically(
                    repo,
                    api_key=openai_api_key,
                    error=error,
                    traceback_text=traceback_text,
                    stage="CONSOLIDATED_FULL_EPISODE_PRODUCTION",
                    progress=progress,
                    owned_modified_paths=owned_modified_paths,
                )
            except SafeTechnicalRepairUserActionRequired:
                raise
            repairs_completed += 1
            _emit(
                progress,
                "تم الإصلاح الآمن رقم "
                + str(repairs_completed)
                + ". إعادة تحميل الوحدات واستكمال المرحلة نفسها.",
                None,
            )
            if result.status != "PASS_SAFE_TECHNICAL_REPAIR":
                raise SafeTechnicalRepairUserActionRequired(
                    "USER_ACTION_REQUIRED:SAFE_REPAIR_DID_NOT_PASS"
                )
