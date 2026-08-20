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
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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


def _canonical_web_url(value: str) -> str:
    # Canonicalise for provenance equality only; do not infer semantic identity.
    text = str(value or "").strip()
    if not text.startswith(("http://", "https://")):
        return text
    try:
        parts = urlsplit(text)
    except ValueError:
        return text

    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if not host:
        return text

    port = parts.port
    if port is not None and not (
        (scheme == "http" and port == 80)
        or (scheme == "https" and port == 443)
    ):
        netloc = f"{host}:{port}"
    else:
        netloc = host

    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")

    tracking = {
        "fbclid",
        "gclid",
        "dclid",
        "mc_cid",
        "mc_eid",
    }
    query_pairs = [
        (key, val)
        for key, val in parse_qsl(
            parts.query,
            keep_blank_values=True,
        )
        if not key.lower().startswith("utm_")
        and key.lower() not in tracking
    ]
    query = urlencode(sorted(query_pairs))
    return urlunsplit((scheme, netloc, path, query, ""))


def _canonical_web_urls(values: Sequence[str]) -> set[str]:
    return {
        _canonical_web_url(str(value))
        for value in values
        if str(value or "").strip().startswith(("http://", "https://"))
    }


def _source_package_web_urls(
    source_packages: Sequence[Mapping[str, Any]],
) -> set[str]:
    result: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            for child in value.values():
                walk(child)
            return
        if isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            for child in value:
                walk(child)
            return
        if isinstance(value, str):
            text = value.strip()
            if text.startswith(("http://", "https://")):
                result.add(text)

    for package in source_packages:
        walk(package)
    return result




# SIRAJ_QURAN_PRIMARY_LOCAL_PROVENANCE_RECONCILIATION_V20_4
def _provider_url_wire_normalized_v20_4(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("[") and "](" in text and text.endswith(")"):
        marker = text.find("](")
        destination = text[marker + 2 : -1].strip()
        if destination.startswith(("http://", "https://")):
            return destination
    if text.startswith("<") and text.endswith(">"):
        destination = text[1:-1].strip()
        if destination.startswith(("http://", "https://")):
            return destination
    return text


def _quran_reference_set_v20_4(value: str) -> set[tuple[int, int]]:
    import re
    from urllib.parse import unquote

    text = unquote(str(value or ""))
    refs: set[tuple[int, int]] = set()

    for match in re.finditer(
        r"(?<!\d)(\d{1,3})\s*[:/]\s*(\d{1,3})(?:\s*-\s*(\d{1,3}))?",
        text,
    ):
        surah = int(match.group(1))
        start = int(match.group(2))
        end = int(match.group(3) or start)

        # Defensive bounds. These are structural guards, not religious claims.
        if surah < 1 or surah > 114:
            continue
        if start < 1 or end < start or end - start > 300:
            continue

        for verse in range(start, end + 1):
            refs.add((surah, verse))

    return refs


def _remap_source_id_v20_4(
    value: Any,
    *,
    old_source_id: str,
    new_source_id: str,
) -> None:
    if isinstance(value, dict):
        source_ids = value.get("source_ids")
        if isinstance(source_ids, list):
            replaced: list[str] = []
            seen: set[str] = set()
            for raw in source_ids:
                sid = str(raw)
                sid = new_source_id if sid == old_source_id else sid
                if sid not in seen:
                    replaced.append(sid)
                    seen.add(sid)
            value["source_ids"] = replaced

        for child in value.values():
            _remap_source_id_v20_4(
                child,
                old_source_id=old_source_id,
                new_source_id=new_source_id,
            )
        return

    if isinstance(value, list):
        for child in value:
            _remap_source_id_v20_4(
                child,
                old_source_id=old_source_id,
                new_source_id=new_source_id,
            )


def _reconcile_unverified_quran_primary_to_local_v20_4(
    dossier: Mapping[str, Any],
    *,
    cited_urls: Sequence[str],
) -> dict[str, Any]:
    # Conservative repair only:
    # - source must claim PRIMARY_OR_CANONICAL_TEXT;
    # - web URL must be quran.com-family and NOT exactly provider-grounded;
    # - exactly one already-present local canonical source must cover every
    #   verse reference claimed by the unsupported row;
    # - facts are remapped to that existing local source;
    # - the unsupported web row is removed rather than relabeled or invented.
    repaired = json.loads(json.dumps(dict(dossier), ensure_ascii=False))
    sources = repaired.get("sources", [])
    if not isinstance(sources, list):
        return repaired

    grounded_exact = {
        _provider_url_wire_normalized_v20_4(str(url)).rstrip("/")
        for url in cited_urls
        if str(url).strip()
    }

    local_rows: list[dict[str, Any]] = []
    for row in sources:
        if not isinstance(row, dict):
            continue
        if str(row.get("authority_class") or "") != "PRIMARY_OR_CANONICAL_TEXT":
            continue
        local_url = str(row.get("url") or "").strip()
        if not local_url.startswith("shamela://local/"):
            continue
        coverage = _quran_reference_set_v20_4(
            str(row.get("title") or "") + " " + local_url
        )
        if coverage:
            local_rows.append(row)

    to_remove: list[dict[str, Any]] = []

    for row in list(sources):
        if not isinstance(row, dict):
            continue
        if str(row.get("authority_class") or "") != "PRIMARY_OR_CANONICAL_TEXT":
            continue

        url = _provider_url_wire_normalized_v20_4(
            str(row.get("url") or "")
        )
        lowered = url.lower()

        if not url.startswith(("http://", "https://")):
            continue
        if "quran.com" not in lowered:
            continue
        if url.rstrip("/") in grounded_exact:
            continue

        claimed_refs = _quran_reference_set_v20_4(
            str(row.get("title") or "") + " " + url
        )
        if not claimed_refs:
            continue

        candidates: list[dict[str, Any]] = []
        for local in local_rows:
            local_refs = _quran_reference_set_v20_4(
                str(local.get("title") or "")
                + " "
                + str(local.get("url") or "")
            )
            if claimed_refs.issubset(local_refs):
                candidates.append(local)

        # Ambiguity stays fail-closed.
        if len(candidates) != 1:
            continue

        local = candidates[0]
        old_id = str(row.get("source_id") or "").strip()
        new_id = str(local.get("source_id") or "").strip()
        if not old_id or not new_id or old_id == new_id:
            continue

        _remap_source_id_v20_4(
            repaired,
            old_source_id=old_id,
            new_source_id=new_id,
        )

        old_dims = row.get("relevance_dimensions")
        new_dims = local.get("relevance_dimensions")
        if isinstance(old_dims, list) and isinstance(new_dims, list):
            merged: list[str] = []
            seen: set[str] = set()
            for raw in [*new_dims, *old_dims]:
                dim = str(raw)
                if dim and dim not in seen:
                    merged.append(dim)
                    seen.add(dim)
            local["relevance_dimensions"] = merged

        to_remove.append(row)

    if to_remove:
        repaired["sources"] = [
            row for row in sources if row not in to_remove
        ]

    return repaired

def _reconcile_source_provenance(
    *,
    dossier: Mapping[str, Any],
    local_context: Mapping[str, Any],
    cited_urls: Sequence[str],
) -> dict[str, Any]:
    # verification_method is derived from durable evidence, not model self-report.
    reconciled = json.loads(
        json.dumps(dict(dossier), ensure_ascii=False)
    )
    reconciled = _reconcile_unverified_quran_primary_to_local_v20_4(
        reconciled,
        cited_urls=cited_urls,
    )

    evidence = local_context.get("evidence_package")
    evidence_urls = _canonical_web_urls(
        tuple(
            _source_urls_from_evidence(
                evidence if isinstance(evidence, Mapping) else None
            )
        )
    )

    shamela = local_context.get("shamela_primary_context")
    shamela_locators = _shamela_locators(
        shamela if isinstance(shamela, Mapping) else {}
    )

    source_packages = local_context.get("source_packages", [])
    if not isinstance(source_packages, Sequence) or isinstance(
        source_packages, (str, bytes)
    ):
        source_packages = []
    package_locators = _source_package_locators(source_packages)
    package_urls = _canonical_web_urls(
        tuple(_source_package_web_urls(source_packages))
    )
    provider_cited = _canonical_web_urls(tuple(cited_urls))

    sources = reconciled.get("sources", [])
    if not isinstance(sources, list):
        raise VisualContextResearchExecutorError(
            "VISUAL_CONTEXT_SOURCES_REQUIRED_FOR_PROVENANCE_RECONCILIATION"
        )

    for source in sources:
        if not isinstance(source, dict):
            raise VisualContextResearchExecutorError(
                "VISUAL_CONTEXT_SOURCE_ROW_INVALID_FOR_PROVENANCE_RECONCILIATION"
            )

        source_id = str(source.get("source_id") or "").strip()
        url = str(source.get("url") or "").strip()
        canonical = _canonical_web_url(url)

        if url.startswith("shamela://local/"):
            if url in shamela_locators or url in package_locators:
                source["verification_method"] = "SHAMELA_LOCAL"
                source["verified"] = True
                continue

        if canonical in evidence_urls:
            source["verification_method"] = "EPISODE_EVIDENCE_PACKAGE"
            source["verified"] = True
            continue

        if canonical in package_urls or url in package_locators:
            source["verification_method"] = "SOURCE_PACKAGE"
            source["verified"] = True
            continue

        if url.startswith(("http://", "https://")):
            if canonical in provider_cited:
                source["verification_method"] = "WEB_SEARCH_TOOL"
                source["verified"] = True
                continue
            raise VisualContextResearchExecutorError(
                "VISUAL_CONTEXT_WEB_SOURCE_NOT_PROVIDER_CITED:"
                + source_id
                + ":"
                + url
            )

        raise VisualContextResearchExecutorError(
            "VISUAL_CONTEXT_SOURCE_PROVENANCE_UNRESOLVED:"
            + source_id
            + ":"
            + url
        )

    return reconciled



def _normalize_duplicate_source_ids(
    dossier: Mapping[str, Any],
) -> dict[str, Any]:
    repaired = json.loads(json.dumps(dict(dossier), ensure_ascii=False))
    sources = repaired.get("sources", [])
    if not isinstance(sources, list):
        raise VisualContextResearchExecutorError(
            "VISUAL_CONTEXT_SOURCES_REQUIRED_FOR_DUPLICATE_ID_NORMALIZATION"
        )

    max_numeric = 0
    for row in sources:
        if not isinstance(row, Mapping):
            continue
        sid = str(row.get("source_id") or "").strip()
        if sid.startswith("VCSRC-") and sid[6:].isdigit():
            max_numeric = max(max_numeric, int(sid[6:]))

    alias_map: dict[str, list[str]] = {}
    seen_first: set[str] = set()

    for row in sources:
        if not isinstance(row, dict):
            raise VisualContextResearchExecutorError(
                "VISUAL_CONTEXT_SOURCE_ROW_INVALID_FOR_DUPLICATE_ID_NORMALIZATION"
            )
        sid = str(row.get("source_id") or "").strip()
        if not sid:
            raise VisualContextResearchExecutorError(
                "VISUAL_CONTEXT_SOURCE_ID_INVALID_OR_DUPLICATE"
            )

        alias_map.setdefault(sid, [])

        if sid not in seen_first:
            seen_first.add(sid)
            alias_map[sid].append(sid)
            continue

        max_numeric += 1
        new_sid = f"VCSRC-{max_numeric:03d}"
        while new_sid in seen_first:
            max_numeric += 1
            new_sid = f"VCSRC-{max_numeric:03d}"

        row["source_id"] = new_sid
        seen_first.add(new_sid)
        alias_map[sid].append(new_sid)

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            source_ids = value.get("source_ids")
            if isinstance(source_ids, list):
                expanded: list[str] = []
                expanded_seen: set[str] = set()
                for raw in source_ids:
                    sid = str(raw)
                    replacements = alias_map.get(sid, [sid])
                    for item in replacements:
                        if item not in expanded_seen:
                            expanded.append(item)
                            expanded_seen.add(item)
                value["source_ids"] = expanded
            for child in value.values():
                _walk(child)
            return
        if isinstance(value, list):
            for child in value:
                _walk(child)

    _walk(repaired)
    return repaired



# SIRAJ_VISUAL_RESEARCH_STRUCTURAL_NORMALIZATION_V17_1
def _quran_route_signature_v17_1(value: str):
    from urllib.parse import unquote

    text = str(value or "").strip()
    if not text.startswith(("http://", "https://")):
        return None
    try:
        parts = urlsplit(text)
    except ValueError:
        return None

    host = (parts.hostname or "").lower()
    if host == "www.quran.com":
        host = "quran.com"
    if host != "quran.com":
        return None

    decoded = unquote(parts.path or "/").strip("/")
    segments = [part for part in decoded.split("/") if part]
    if not segments:
        return None

    surah = None
    ayah = None
    tail = []

    first = segments[0]
    if ":" in first:
        left, right = first.split(":", 1)
        if left.isdigit() and right.isdigit():
            surah = int(left)
            ayah = int(right)
            tail = segments[1:]
    elif (
        len(segments) >= 2
        and segments[0].isdigit()
        and segments[1].isdigit()
    ):
        surah = int(segments[0])
        ayah = int(segments[1])
        tail = segments[2:]
    elif first.isdigit():
        surah = int(first)
        query = {
            str(key).strip().casefold(): str(val).strip()
            for key, val in parse_qsl(
                parts.query,
                keep_blank_values=True,
            )
        }
        for key in (
            "startingverse",
            "verse",
            "ayah",
            "ayahno",
            "verse_number",
        ):
            val = query.get(key)
            if val and val.isdigit():
                ayah = int(val)
                break
        tail = segments[1:]

    if surah is None or ayah is None:
        return None

    return (
        (surah, ayah),
        tuple(part.casefold() for part in tail),
    )


def _altafsir_identity_v17_1(value: str):
    text = str(value or "").strip()
    if not text.startswith(("http://", "https://")):
        return None
    try:
        parts = urlsplit(text)
    except ValueError:
        return None

    host = (parts.hostname or "").lower()
    if host == "www.altafsir.com":
        host = "altafsir.com"
    if host != "altafsir.com":
        return None

    path = (parts.path or "/").rstrip("/").casefold() or "/"
    aliases = {
        "languageid": "languageid",
        "userprofile": "userprofile",
        "page": "page",
        "size": "size",
        "ayahno": "ayahno",
        "tayahno": "ayahno",
        "display": "display",
        "tdisplay": "display",
        "madhno": "madhno",
        "tmadhno": "madhno",
        "sorano": "sorano",
        "tsorano": "sorano",
        "tafsirno": "tafsirno",
        "ttafsirno": "tafsirno",
    }

    identity = {}
    for key, val in parse_qsl(
        parts.query,
        keep_blank_values=True,
    ):
        normalized = aliases.get(str(key).strip().casefold())
        if normalized is not None:
            identity[normalized] = str(val).strip()

    return host, path, identity


def _provider_exact_url_v17_1(
    source_url: str,
    cited_urls: Sequence[str],
):
    source_text = str(source_url or "").strip()
    citations = tuple(
        str(value).strip()
        for value in cited_urls
        if str(value or "").strip().startswith(("http://", "https://"))
    )

    canonical = _canonical_web_url(source_text)
    exact = list(
        dict.fromkeys(
            value
            for value in citations
            if _canonical_web_url(value) == canonical
        )
    )
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None

    quran_signature = _quran_route_signature_v17_1(source_text)
    if quran_signature is not None:
        quran_matches = list(
            dict.fromkeys(
                value
                for value in citations
                if _quran_route_signature_v17_1(value)
                == quran_signature
            )
        )
        if len(quran_matches) == 1:
            return quran_matches[0]

    altafsir = _altafsir_identity_v17_1(source_text)
    if altafsir is not None:
        source_host, source_path, source_fields = altafsir
        if (
            {"ayahno", "tafsirno"}.issubset(source_fields)
            and len(source_fields) >= 4
        ):
            matches = []
            for candidate in citations:
                parsed = _altafsir_identity_v17_1(candidate)
                if parsed is None:
                    continue
                host, path, fields = parsed
                if host != source_host or path != source_path:
                    continue
                if all(
                    fields.get(key) == value
                    for key, value in source_fields.items()
                ):
                    matches.append(candidate)
            matches = list(dict.fromkeys(matches))
            if len(matches) == 1:
                return matches[0]

    return None


def _normalize_provider_urls_v17_1(
    dossier: Mapping[str, Any],
    *,
    cited_urls: Sequence[str],
):
    repaired = json.loads(
        json.dumps(dict(dossier), ensure_ascii=False)
    )
    sources = repaired.get("sources", [])
    if not isinstance(sources, list):
        return repaired

    for source in sources:
        if not isinstance(source, dict):
            continue
        url = str(source.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        exact = _provider_exact_url_v17_1(url, cited_urls)
        if exact is not None:
            source["url"] = exact

    return repaired


def _normalize_duplicate_source_ids_v17_1(
    dossier: Mapping[str, Any],
):
    repaired = json.loads(
        json.dumps(dict(dossier), ensure_ascii=False)
    )
    sources = repaired.get("sources", [])
    if not isinstance(sources, list):
        return repaired

    max_numeric = 0
    for row in sources:
        if not isinstance(row, Mapping):
            continue
        sid = str(row.get("source_id") or "").strip()
        if sid.startswith("VCSRC-") and sid[6:].isdigit():
            max_numeric = max(max_numeric, int(sid[6:]))

    aliases = {}
    seen = set()

    for row in sources:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("source_id") or "").strip()
        if not sid:
            continue

        aliases.setdefault(sid, [])
        if sid not in seen:
            seen.add(sid)
            aliases[sid].append(sid)
            continue

        max_numeric += 1
        replacement = f"VCSRC-{max_numeric:03d}"
        while replacement in seen:
            max_numeric += 1
            replacement = f"VCSRC-{max_numeric:03d}"

        row["source_id"] = replacement
        seen.add(replacement)
        aliases[sid].append(replacement)

    if not any(len(values) > 1 for values in aliases.values()):
        return repaired

    def walk(value):
        if isinstance(value, dict):
            source_ids = value.get("source_ids")
            if isinstance(source_ids, list):
                expanded = []
                expanded_seen = set()
                for raw in source_ids:
                    sid = str(raw).strip()
                    replacements = aliases.get(sid, [sid])
                    for replacement in replacements:
                        if (
                            replacement
                            and replacement not in expanded_seen
                        ):
                            expanded.append(replacement)
                            expanded_seen.add(replacement)
                value["source_ids"] = expanded
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(repaired)
    return repaired


def _normalize_fact_graph_v17_1(
    dossier: Mapping[str, Any],
):
    from src.application.visual_context_research_v1 import (
        ASSERTIVE_CERTAINTY,
    )

    repaired = json.loads(
        json.dumps(dict(dossier), ensure_ascii=False)
    )
    sources = repaired.get("sources", [])
    dimensions = repaired.get("dimensions")

    if not isinstance(sources, list) or not isinstance(
        dimensions,
        Mapping,
    ):
        return repaired

    sources_by_id = {}
    for row in sources:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("source_id") or "").strip()
        if sid and sid not in sources_by_id:
            sources_by_id[sid] = row

    required_dimensions = {
        sid: set()
        for sid in sources_by_id
    }

    for dimension_name, dimension in dimensions.items():
        if not isinstance(dimension, Mapping):
            continue
        facts = dimension.get("facts", [])
        if not isinstance(facts, list):
            continue

        for fact in facts:
            if not isinstance(fact, dict):
                continue

            raw_source_ids = [
                str(value).strip()
                for value in fact.get("source_ids", [])
                if str(value).strip()
            ]
            valid_source_ids = [
                sid
                for sid in raw_source_ids
                if sid in sources_by_id
            ]
            unknown_source_ids = [
                sid
                for sid in raw_source_ids
                if sid not in sources_by_id
            ]

            # Remove only orphan pointers when the fact retains at least one
            # real registered source. Never invent evidence.
            if unknown_source_ids and valid_source_ids:
                fact["source_ids"] = valid_source_ids
                raw_source_ids = valid_source_ids

            certainty = str(fact.get("certainty") or "").strip()
            if fact.get("assertive_visualization") is True:
                if (
                    not raw_source_ids
                    or certainty not in ASSERTIVE_CERTAINTY
                ):
                    fact["assertive_visualization"] = False

            for sid in raw_source_ids:
                if sid in required_dimensions:
                    required_dimensions[sid].add(
                        str(dimension_name)
                    )

    for sid, required in required_dimensions.items():
        source = sources_by_id[sid]
        current_raw = source.get("relevance_dimensions", [])
        current = [
            str(value).strip()
            for value in current_raw
            if str(value).strip()
        ] if isinstance(current_raw, list) else []
        seen = set(current)
        for dimension_name in sorted(required):
            if dimension_name not in seen:
                current.append(dimension_name)
                seen.add(dimension_name)
        source["relevance_dimensions"] = current

    return repaired


def _structural_preflight_v17_1(
    dossier: Mapping[str, Any],
):
    from src.application.visual_context_research_v1 import (
        ASSERTIVE_CERTAINTY,
    )

    issues = []
    sources = dossier.get("sources", [])
    dimensions = dossier.get("dimensions")

    if not isinstance(sources, list):
        return
    if not isinstance(dimensions, Mapping):
        return

    sources_by_id = {}
    for index, row in enumerate(sources):
        if not isinstance(row, Mapping):
            issues.append(
                {"type": "SOURCE_ROW_INVALID", "index": index}
            )
            continue
        sid = str(row.get("source_id") or "").strip()
        if not sid:
            issues.append(
                {"type": "SOURCE_ID_EMPTY", "index": index}
            )
            continue
        if sid in sources_by_id:
            issues.append(
                {"type": "SOURCE_ID_DUPLICATE", "source_id": sid}
            )
            continue
        sources_by_id[sid] = row

    for dimension_name, dimension in dimensions.items():
        if not isinstance(dimension, Mapping):
            continue
        facts = dimension.get("facts", [])
        if not isinstance(facts, list):
            continue

        for fact in facts:
            if not isinstance(fact, Mapping):
                continue
            fact_id = str(fact.get("fact_id") or "")
            source_ids = [
                str(value).strip()
                for value in fact.get("source_ids", [])
                if str(value).strip()
            ]
            certainty = str(fact.get("certainty") or "").strip()

            for sid in source_ids:
                source = sources_by_id.get(sid)
                if source is None:
                    issues.append(
                        {
                            "type": "FACT_SOURCE_UNKNOWN",
                            "dimension": str(dimension_name),
                            "fact_id": fact_id,
                            "source_id": sid,
                        }
                    )
                    continue
                relevance = {
                    str(value)
                    for value in source.get(
                        "relevance_dimensions",
                        [],
                    )
                }
                if str(dimension_name) not in relevance:
                    issues.append(
                        {
                            "type": "FACT_SOURCE_DIMENSION_MISMATCH",
                            "dimension": str(dimension_name),
                            "fact_id": fact_id,
                            "source_id": sid,
                        }
                    )

            if fact.get("assertive_visualization") is True:
                if not source_ids:
                    issues.append(
                        {
                            "type": "ASSERTIVE_WITHOUT_SOURCE",
                            "dimension": str(dimension_name),
                            "fact_id": fact_id,
                        }
                    )
                if certainty not in ASSERTIVE_CERTAINTY:
                    issues.append(
                        {
                            "type": "ASSERTIVE_CERTAINTY_TOO_LOW",
                            "dimension": str(dimension_name),
                            "fact_id": fact_id,
                            "certainty": certainty,
                        }
                    )

    if issues:
        raise VisualContextResearchExecutorError(
            "VISUAL_CONTEXT_STRUCTURAL_PREFLIGHT_FAILED_V17_1:"
            + json.dumps(
                issues,
                ensure_ascii=False,
                sort_keys=True,
            )
        )


def _normalize_provider_output_v17_1(
    dossier: Mapping[str, Any],
    *,
    cited_urls: Sequence[str],
):
    value = _normalize_provider_urls_v17_1(
        dossier,
        cited_urls=cited_urls,
    )
    value = _normalize_duplicate_source_ids_v17_1(value)
    value = _normalize_fact_graph_v17_1(value)
    _structural_preflight_v17_1(value)
    return value


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
    cited = _canonical_web_urls(tuple(cited_urls))
    evidence_urls = _canonical_web_urls(
        tuple(
            _source_urls_from_evidence(
                local_context.get("evidence_package")
                if isinstance(local_context, Mapping)
                else None
            )
        )
    )
    shamela = local_context.get("shamela_primary_context")
    shamela_locators = _shamela_locators(
        shamela if isinstance(shamela, Mapping) else {}
    )
    source_packages = (
        local_context.get("source_packages", [])
        if isinstance(local_context, Mapping)
        else []
    )
    package_locators = _source_package_locators(source_packages)
    package_urls = _canonical_web_urls(
        tuple(_source_package_web_urls(source_packages))
    )

    for source in dossier.get("sources", []):
        if not isinstance(source, Mapping):
            continue
        source_id = str(source.get("source_id") or "")
        url = str(source.get("url") or "").strip()
        method = str(source.get("verification_method") or "").strip()

        if method == "WEB_SEARCH_TOOL":
            if (
                not url.startswith(("http://", "https://"))
                or _canonical_web_url(url) not in cited
            ):
                raise VisualContextResearchExecutorError(
                    "VISUAL_CONTEXT_WEB_SOURCE_NOT_PROVIDER_CITED:"
                    + source_id
                    + ":"
                    + url
                )
        elif method == "EPISODE_EVIDENCE_PACKAGE":
            if _canonical_web_url(url) not in evidence_urls:
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
            if (
                url not in package_locators
                and _canonical_web_url(url) not in package_urls
                and _canonical_web_url(url) not in evidence_urls
            ):
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

    provider_dossier = provider_result.payload
    if provider_dossier.get("episode_id") != episode_id:
        raise VisualContextResearchExecutorError(
            "VISUAL_CONTEXT_PROVIDER_EPISODE_MISMATCH"
        )
    if provider_dossier.get("context_id") != context_id:
        raise VisualContextResearchExecutorError(
            "VISUAL_CONTEXT_PROVIDER_CONTEXT_MISMATCH"
        )

    local_context = request["local_context"]
    provider_dossier = _normalize_provider_output_v17_1(
        provider_dossier,
        cited_urls=provider_result.cited_urls,
    )
    dossier = _reconcile_source_provenance(
        dossier=provider_dossier,
        local_context=local_context,
        cited_urls=provider_result.cited_urls,
    )
    dossier = _normalize_duplicate_source_ids(dossier)
    dossier = _normalize_provider_output_v17_1(
        dossier,
        cited_urls=provider_result.cited_urls,
    )
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
