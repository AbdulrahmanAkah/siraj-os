"""Series-wide Visual Context Research executor.

The executor is provider-agnostic and performs exactly one provider invocation
when research is required. Transport/provider authorization is deliberately
outside this module so a Desktop-only paid boundary can wrap it without a CLI
escape hatch.

Responsibilities:
- collect all currently available local research context;
- build a source-class/dimension sweep request;
- require source provenance for every external fact;
- reconcile/validate the returned dossier;
- persist the canonical dossier atomically with history on explicit refresh;
- never retry or resubmit automatically.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from src.application.shamela_primary_research_v1 import (
    build_shamela_primary_context,
)
from src.application.visual_context_research_v1 import (
    REQUIRED_DIMENSIONS,
    VisualContextResearchError,
    build_research_request,
    dossier_path,
    load_series_policy,
    validate_visual_context_dossier,
)

EXECUTOR_VERSION = "siraj-visual-context-research-executor-v1"
RECEIPT_DIRNAME = "visual-context-research-receipts-v1"
HISTORY_DIRNAME = "history"

MAX_LOCAL_JSON_BYTES = 8 * 1024 * 1024
MAX_SOURCE_PACKAGES = 12

ProviderCall = Callable[[Mapping[str, Any]], "VisualResearchProviderResult"]


class VisualContextResearchExecutorError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class VisualResearchProviderResult:
    payload: dict[str, Any]
    provider: str
    model: str
    provider_response_id: str
    web_search_calls: int
    cited_urls: tuple[str, ...]
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    estimated_cost_usd: float = 0.0


@dataclass(frozen=True, slots=True)
class VisualContextResearchExecutionResult:
    episode_id: str
    context_id: str
    status: str
    dossier_path: Path
    dossier_sha256: str
    receipt_path: Path
    provider_calls: int
    web_search_calls: int
    reused_existing: bool
    archived_previous_path: Path | None


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(
        json.dumps(
            dict(payload),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    os.replace(temporary, path)


def _read_json_optional(path: Path) -> dict[str, Any] | None:
    try:
        if (
            not path.is_file()
            or path.stat().st_size > MAX_LOCAL_JSON_BYTES
        ):
            return None
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _episode_root(repo_root: Path, episode_id: str) -> Path:
    root = Path(repo_root).resolve() / "projects" / episode_id
    if not root.is_dir():
        raise VisualContextResearchExecutorError(
            "VISUAL_CONTEXT_EPISODE_ROOT_MISSING:" + str(root)
        )
    return root


def _source_urls_from_evidence(
    evidence: Mapping[str, Any] | None,
) -> set[str]:
    if not isinstance(evidence, Mapping):
        return set()
    result: set[str] = set()
    for row in evidence.get("source_register", []):
        if not isinstance(row, Mapping):
            continue
        url = str(row.get("url") or "").strip()
        if url:
            result.add(url)
    return result


def _shamela_locators(context: Mapping[str, Any]) -> set[str]:
    result: set[str] = set()
    for source in context.get("sources", []):
        if not isinstance(source, Mapping):
            continue
        for excerpt in source.get("excerpts", []):
            if not isinstance(excerpt, Mapping):
                continue
            locator = str(excerpt.get("locator") or "").strip()
            if locator:
                result.add(locator)
    return result


def _source_package_context(episode_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    contracts = episode_root / "contracts"
    if not contracts.is_dir():
        return rows
    for path in sorted(contracts.glob("source-package-v1*.json"))[
        :MAX_SOURCE_PACKAGES
    ]:
        payload = _read_json_optional(path)
        if payload is None:
            continue
        rows.append(
            {
                "path": str(path.relative_to(episode_root)).replace("\\", "/"),
                "payload": payload,
            }
        )
    return rows


def _source_package_locators(
    source_packages: Sequence[Mapping[str, Any]],
) -> set[str]:
    result: set[str] = set()
    for package in source_packages:
        serialized = json.dumps(package, ensure_ascii=False)
        for token in serialized.replace('"', " ").split():
            cleaned = token.rstrip(",;)]}")
            if cleaned.startswith("shamela://local/"):
                result.add(cleaned)
    return result


def _infer_domain_profile(
    *,
    evidence: Mapping[str, Any] | None,
    narration_text: str,
    visual_brief: Mapping[str, Any],
) -> str:
    source_types = {
        str(row.get("source_type") or "")
        for row in (evidence or {}).get("source_register", [])
        if isinstance(row, Mapping)
    }
    if source_types & {
        "QURAN",
        "HADITH_COLLECTION",
        "CLASSICAL_SOURCE",
        "SHAMELA_LOCAL_BOOK",
    }:
        return "ISLAMIC_RELIGIOUS_HISTORY"

    text = (
        narration_text
        + " "
        + json.dumps(dict(visual_brief), ensure_ascii=False)
    ).lower()
    islamic_cues = (
        "quran",
        "hadith",
        "islam",
        "allah",
        "adam",
        "musa",
        "hawwa",
        "جنة",
        "الجنة",
        "آدم",
        "موسى",
        "حواء",
        "القرآن",
        "حديث",
    )
    if any(cue in text for cue in islamic_cues):
        return "ISLAMIC_RELIGIOUS_HISTORY"

    history_cues = (
        "ancient",
        "historical",
        "century",
        "dynasty",
        "empire",
        "war",
        "archaeolog",
        "تاريخ",
        "قديم",
        "حقبة",
        "قرن",
        "إمبراطورية",
        "حرب",
    )
    if any(cue in text for cue in history_cues):
        return "HISTORY"

    science_cues = (
        "science",
        "physics",
        "biology",
        "chemistry",
        "astronomy",
        "geology",
        "علم",
        "فيزياء",
        "أحياء",
        "كيمياء",
        "فلك",
    )
    if any(cue in text for cue in science_cues):
        return "SCIENCE"

    return "GENERAL_DOCUMENTARY"


def collect_local_research_context(
    repo_root: Path,
    *,
    episode_id: str,
    context_id: str,
    narration_text: str,
    visual_brief: Mapping[str, Any],
) -> dict[str, Any]:
    root = _episode_root(repo_root, episode_id)

    evidence = _read_json_optional(root / "research/evidence-package-v1.json")
    approved_scope = _read_json_optional(
        root / "contracts/approved-scope-v1.json"
    )
    script = _read_json_optional(root / "script/episode-script-v1.json")
    storyboard = _read_json_optional(
        root / "cinematic/storyboard-and-media-plan-v1.json"
    )
    source_packages = _source_package_context(root)

    domain_profile = _infer_domain_profile(
        evidence=evidence,
        narration_text=narration_text,
        visual_brief=visual_brief,
    )

    shamela_query = {
        "episode_id": episode_id,
        "context_id": context_id,
        "narration_text": narration_text,
        "visual_brief": dict(visual_brief),
        "approved_scope": approved_scope or {},
    }
    shamela = build_shamela_primary_context(
        Path(repo_root).resolve(),
        shamela_query,
        require_excerpts=False,
    )

    return {
        "schema_version": "siraj-visual-context-local-context-v1",
        "episode_id": episode_id,
        "context_id": context_id,
        "domain_profile": domain_profile,
        "evidence_package": evidence,
        "approved_scope": approved_scope,
        "script_package": script,
        "storyboard_package": storyboard,
        "source_packages": source_packages,
        "shamela_primary_context": shamela,
        "available_local_source_classes": {
            "EPISODE_EVIDENCE_PACKAGE": evidence is not None,
            "APPROVED_SCOPE": approved_scope is not None,
            "SCRIPT_PACKAGE": script is not None,
            "STORYBOARD_PACKAGE": storyboard is not None,
            "SOURCE_PACKAGES": bool(source_packages),
            "SHAMELA_LOCAL": bool(shamela.get("sources")),
        },
    }


def build_executor_request(
    repo_root: Path,
    *,
    episode_id: str,
    context_id: str,
    narration_text: str,
    visual_brief: Mapping[str, Any],
) -> dict[str, Any]:
    policy = load_series_policy(repo_root)
    local_context = collect_local_research_context(
        repo_root,
        episode_id=episode_id,
        context_id=context_id,
        narration_text=narration_text,
        visual_brief=visual_brief,
    )
    base = build_research_request(
        episode_id=episode_id,
        context_id=context_id,
        narration_text=narration_text,
        visual_brief=visual_brief,
        domain_profile=local_context["domain_profile"],
    )

    source_classes = [
        dict(row)
        for row in policy.get("source_classes", [])
        if isinstance(row, Mapping)
    ]

    return {
        "schema_version": "siraj-visual-context-provider-request-v1",
        "executor_version": EXECUTOR_VERSION,
        "episode_id": episode_id,
        "context_id": context_id,
        "domain_profile": local_context["domain_profile"],
        "series_policy": policy,
        "research_request": base,
        "local_context": local_context,
        "source_sweep": {
            "required_source_classes": [
                str(row.get("id"))
                for row in source_classes
                if row.get("required_to_check") is True
            ],
            "source_classes": source_classes,
            "all_configured_classes_must_be_checked_or_unavailable": True,
            "web_search_required_for_external_source_classes": True,
            "cross_source_reconciliation_required": True,
            "no_early_stop_after_first_plausible_source": True,
        },
        "dossier_requirements": {
            "schema_version": "siraj-visual-context-dossier-v1",
            "required_dimensions": list(REQUIRED_DIMENSIONS),
            "face_visibility": "FORBIDDEN_WITHOUT_EXCEPTION",
            "head_required": False,
            "motion_safe_face_exclusion": True,
            "narration_silence_policy": "RESEARCH_NOT_INVENT",
            "weak_evidence_policy": "NEUTRAL_NON_ASSERTIVE_DEPICTION",
            "source_conflict_policy": "FAIL_CLOSED_UNTIL_RECONCILED",
        },
    }


def _verify_source_provenance(
    *,
    dossier: Mapping[str, Any],
    local_context: Mapping[str, Any],
    cited_urls: Sequence[str],
) -> None:
    cited = {str(url).strip() for url in cited_urls if str(url).strip()}
    evidence_urls = _source_urls_from_evidence(
        local_context.get("evidence_package")
        if isinstance(local_context, Mapping)
        else None
    )
    shamela = local_context.get("shamela_primary_context")
    shamela_locators = _shamela_locators(
        shamela if isinstance(shamela, Mapping) else {}
    )
    package_locators = _source_package_locators(
        local_context.get("source_packages", [])
        if isinstance(local_context, Mapping)
        else []
    )

    for source in dossier.get("sources", []):
        if not isinstance(source, Mapping):
            continue
        source_id = str(source.get("source_id") or "")
        url = str(source.get("url") or "").strip()
        method = str(source.get("verification_method") or "").strip()

        if method == "WEB_SEARCH_TOOL":
            if not url.startswith(("http://", "https://")) or url not in cited:
                raise VisualContextResearchExecutorError(
                    "VISUAL_CONTEXT_WEB_SOURCE_NOT_PROVIDER_CITED:"
                    + source_id
                    + ":"
                    + url
                )
        elif method == "EPISODE_EVIDENCE_PACKAGE":
            if url not in evidence_urls:
                raise VisualContextResearchExecutorError(
                    "VISUAL_CONTEXT_EVIDENCE_SOURCE_NOT_LOCAL:"
                    + source_id
                    + ":"
                    + url
                )
        elif method == "SHAMELA_LOCAL":
            if url not in shamela_locators and url not in package_locators:
                raise VisualContextResearchExecutorError(
                    "VISUAL_CONTEXT_SHAMELA_SOURCE_NOT_LOCAL:"
                    + source_id
                    + ":"
                    + url
                )
        elif method == "SOURCE_PACKAGE":
            if url not in package_locators and url not in evidence_urls:
                raise VisualContextResearchExecutorError(
                    "VISUAL_CONTEXT_SOURCE_PACKAGE_PROVENANCE_FAILED:"
                    + source_id
                    + ":"
                    + url
                )
        else:
            raise VisualContextResearchExecutorError(
                "VISUAL_CONTEXT_SOURCE_VERIFICATION_METHOD_INVALID:"
                + source_id
                + ":"
                + method
            )


def _receipt_path(
    repo_root: Path,
    *,
    episode_id: str,
    context_id: str,
) -> Path:
    return (
        Path(repo_root).resolve()
        / "projects"
        / episode_id
        / "research"
        / RECEIPT_DIRNAME
        / f"{context_id}.json"
    )


def _archive_existing(
    current: Path,
    *,
    context_id: str,
) -> Path:
    raw = current.read_bytes()
    digest = _sha256_bytes(raw)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = (
        current.parent
        / HISTORY_DIRNAME
        / context_id
        / f"{stamp}-{digest[:16]}.json"
    )
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        raise VisualContextResearchExecutorError(
            "VISUAL_CONTEXT_HISTORY_COLLISION:" + str(archive)
        )
    archive.write_bytes(raw)
    return archive


def execute_visual_context_research(
    repo_root: Path,
    *,
    episode_id: str,
    context_id: str,
    narration_text: str,
    visual_brief: Mapping[str, Any],
    provider_call: ProviderCall,
    refresh_existing: bool = False,
    refresh_reason: str = "",
) -> VisualContextResearchExecutionResult:
    """Run one research attempt or reuse the existing validated dossier.

    There is deliberately no retry loop.
    """

    repo_root = Path(repo_root).resolve()
    policy = load_series_policy(repo_root)
    target = dossier_path(
        repo_root,
        episode_id=episode_id,
        context_id=context_id,
    )
    receipt_path = _receipt_path(
        repo_root,
        episode_id=episode_id,
        context_id=context_id,
    )

    if target.is_file() and not refresh_existing:
        existing = json.loads(target.read_text(encoding="utf-8-sig"))
        validate_visual_context_dossier(
            dossier=existing,
            policy=policy,
            episode_id=episode_id,
            context_id=context_id,
        )
        digest = _sha256_bytes(target.read_bytes())
        return VisualContextResearchExecutionResult(
            episode_id=episode_id,
            context_id=context_id,
            status="REUSED_VALIDATED_EXISTING_DOSSIER",
            dossier_path=target,
            dossier_sha256=digest,
            receipt_path=receipt_path,
            provider_calls=0,
            web_search_calls=0,
            reused_existing=True,
            archived_previous_path=None,
        )

    if refresh_existing and not str(refresh_reason).strip():
        raise VisualContextResearchExecutorError(
            "VISUAL_CONTEXT_REFRESH_REASON_REQUIRED"
        )

    request = build_executor_request(
        repo_root,
        episode_id=episode_id,
        context_id=context_id,
        narration_text=narration_text,
        visual_brief=visual_brief,
    )
    request_sha = _sha256_bytes(_canonical_json_bytes(request))

    # Exactly one injected provider call. Any exception propagates; automatic
    # retry/resubmission is forbidden.
    provider_result = provider_call(request)
    if not isinstance(provider_result, VisualResearchProviderResult):
        raise VisualContextResearchExecutorError(
            "VISUAL_CONTEXT_PROVIDER_RESULT_TYPE_INVALID"
        )

    dossier = provider_result.payload
    if dossier.get("episode_id") != episode_id:
        raise VisualContextResearchExecutorError(
            "VISUAL_CONTEXT_PROVIDER_EPISODE_MISMATCH"
        )
    if dossier.get("context_id") != context_id:
        raise VisualContextResearchExecutorError(
            "VISUAL_CONTEXT_PROVIDER_CONTEXT_MISMATCH"
        )

    local_context = request["local_context"]
    _verify_source_provenance(
        dossier=dossier,
        local_context=local_context,
        cited_urls=provider_result.cited_urls,
    )
    validated = validate_visual_context_dossier(
        dossier=dossier,
        policy=policy,
        episode_id=episode_id,
        context_id=context_id,
    )

    archived: Path | None = None
    if target.is_file():
        archived = _archive_existing(target, context_id=context_id)

    _atomic_json(target, validated)
    digest = _sha256_bytes(target.read_bytes())

    receipt = {
        "schema_version": "siraj-visual-context-research-receipt-v1",
        "executor_version": EXECUTOR_VERSION,
        "episode_id": episode_id,
        "context_id": context_id,
        "status": "COMPLETE",
        "request_sha256": request_sha,
        "dossier_path": str(
            target.relative_to(repo_root)
        ).replace("\\", "/"),
        "dossier_sha256": digest,
        "provider": provider_result.provider,
        "model": provider_result.model,
        "provider_response_id": provider_result.provider_response_id,
        "provider_calls": 1,
        "automatic_retry": False,
        "automatic_resubmission": False,
        "web_search_calls": provider_result.web_search_calls,
        "cited_url_count": len(set(provider_result.cited_urls)),
        "usage": {
            "input_tokens": provider_result.input_tokens,
            "output_tokens": provider_result.output_tokens,
            "cached_input_tokens": provider_result.cached_input_tokens,
            "estimated_cost_usd": provider_result.estimated_cost_usd,
        },
        "refresh_existing": bool(refresh_existing),
        "refresh_reason": str(refresh_reason).strip() or None,
        "archived_previous_path": (
            str(archived.relative_to(repo_root)).replace("\\", "/")
            if archived is not None
            else None
        ),
        "completed_at_utc": _now_utc(),
    }
    _atomic_json(receipt_path, receipt)

    return VisualContextResearchExecutionResult(
        episode_id=episode_id,
        context_id=context_id,
        status="COMPLETE",
        dossier_path=target,
        dossier_sha256=digest,
        receipt_path=receipt_path,
        provider_calls=1,
        web_search_calls=provider_result.web_search_calls,
        reused_existing=False,
        archived_previous_path=archived,
    )
