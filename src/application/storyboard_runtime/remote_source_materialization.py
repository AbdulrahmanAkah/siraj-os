"""Fetch, archive, and machine-extract Adam source candidates.

Network retrieval and anchor comparison are mechanical preparation steps only.
No fetched record becomes source_verified, authenticated, origin-classified,
human-approved, binding-ready, or provider-enabled.
"""
from __future__ import annotations

import concurrent.futures
import csv
import hashlib
import html
from html.parser import HTMLParser
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

MATERIALIZATION_SCHEMA = "siraj-remote-source-materialization-v1"
FETCH_SCHEMA = "siraj-remote-source-fetch-manifest-v1"
POLICY_SCHEMA = "siraj-remote-source-materialization-policy-v1"
REVIEW_SCHEMA = "siraj-remote-source-human-review-template-v1"
PREFILL_SCHEMA = "siraj-remote-source-prefill-suggestion-pack-v1"
STATUS = "REMOTE_SOURCE_MATERIALIZED_HUMAN_COMPARISON_PENDING"
GATE = "WITHHELD_PENDING_APPROVED_EVIDENCE_PACKAGE"
AUTO_APPROVAL = "FORBIDDEN"
LIVE_EXECUTION = "BLOCKED"

EXPECTED_CATALOG_SCHEMA = "siraj-external-source-candidate-catalog-v1"
EXPECTED_PACK_SCHEMA = "siraj-external-event-source-candidate-pack-v1"
EXPECTED_SOURCE_COUNT = 22
EXPECTED_EVENT_COUNT = 14
EXPECTED_LINK_COUNT = 28
MAX_RESPONSE_BYTES = 8_000_000
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_RETRIES = 2

ARABIC_MARK_RE = re.compile(r"[\u0600-\u06ff]")
DIACRITICS_RE = re.compile(
    r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]"
)
QURAN_LOCATOR_RE = re.compile(r"^Quran\s+(\d+):(\d+)(?:-(\d+))?$")
TEXT_UTHMANI_RE = re.compile(
    r'"text_uthmani"\s*:\s*("(?:\\.|[^"\\])*")'
)
BLOCK_TAGS = {
    "article", "blockquote", "div", "li", "main", "p", "section",
    "span", "td",
}
IGNORED_TAGS = {"script", "style", "noscript", "svg", "template"}


class RemoteSourceMaterializationError(ValueError):
    pass


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def bytes_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RemoteSourceMaterializationError(f"Invalid JSON: {path}") from exc


def write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def normalize_arabic(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = DIACRITICS_RE.sub("", value)
    value = value.replace("\u0640", "")
    replacements = {
        "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
        "ى": "ي", "ؤ": "و", "ئ": "ي",
        "ة": "ه",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    value = re.sub(r"[^\u0600-\u06ff0-9A-Za-z]+", " ", value)
    return " ".join(value.split()).strip()


def anchor_metrics(anchor: str, extracted: str) -> dict:
    anchor_norm = normalize_arabic(anchor)
    extracted_norm = normalize_arabic(extracted)
    anchor_tokens = anchor_norm.split()
    extracted_tokens = extracted_norm.split()
    anchor_set = set(anchor_tokens)
    extracted_set = set(extracted_tokens)
    overlap = anchor_set & extracted_set
    coverage = len(overlap) / len(anchor_set) if anchor_set else 0.0
    ordered_substring = bool(anchor_norm and anchor_norm in extracted_norm)
    return {
        "anchor_token_count": len(anchor_tokens),
        "extracted_token_count": len(extracted_tokens),
        "overlap_token_count": len(overlap),
        "anchor_token_coverage": round(coverage, 6),
        "normalized_anchor_is_substring": ordered_substring,
        "normalized_anchor_sha256": text_sha256(anchor_norm),
        "normalized_extracted_sha256": text_sha256(extracted_norm),
    }


class _BlockTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack: list[dict] = []
        self._ignored_depth = 0
        self.blocks: list[dict] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered in IGNORED_TAGS:
            self._ignored_depth += 1
        attrs_map = {key.lower(): value or "" for key, value in attrs}
        node = {
            "tag": lowered,
            "classes": tuple(attrs_map.get("class", "").split()),
            "id": attrs_map.get("id", ""),
            "texts": [],
            "ignored": self._ignored_depth > 0,
        }
        self._stack.append(node)

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self._ignored_depth or not data.strip():
            return
        for node in self._stack:
            if not node["ignored"]:
                node["texts"].append(data)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        node = None
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index]["tag"] == lowered:
                node = self._stack.pop(index)
                break
        if node is not None and lowered in BLOCK_TAGS and not node["ignored"]:
            text = " ".join(" ".join(node["texts"]).split())
            if text:
                self.blocks.append({
                    "tag": node["tag"],
                    "classes": list(node["classes"]),
                    "id": node["id"],
                    "text": text,
                })
        if lowered in IGNORED_TAGS and self._ignored_depth:
            self._ignored_depth -= 1


def html_text_blocks(raw: bytes, charset: str = "utf-8") -> list[dict]:
    text = raw.decode(charset, errors="replace")
    parser = _BlockTextParser()
    parser.feed(text)
    seen = set()
    blocks = []
    for block in parser.blocks:
        normalized = " ".join(block["text"].split())
        key = text_sha256(normalized)
        if key in seen:
            continue
        seen.add(key)
        block = dict(block)
        block["text"] = normalized
        blocks.append(block)
    return blocks


def choose_hadith_arabic_block(raw: bytes, anchor: str) -> dict:
    candidates = []
    for block in html_text_blocks(raw):
        text = block["text"]
        if len(ARABIC_MARK_RE.findall(text)) < 12:
            continue
        metrics = anchor_metrics(anchor, text)
        classes = {value.lower() for value in block["classes"]}
        class_bonus = 0
        if any("arabic_hadith_full" in value for value in classes):
            class_bonus += 0.30
        elif any("arabic" in value for value in classes):
            class_bonus += 0.12
        length_penalty = min(max(len(text) - 5000, 0) / 20000, 0.2)
        score = (
            metrics["anchor_token_coverage"]
            + (0.25 if metrics["normalized_anchor_is_substring"] else 0)
            + class_bonus
            - length_penalty
        )
        candidates.append({
            "score": round(score, 6),
            "block": block,
            "metrics": metrics,
        })
    if not candidates:
        return {
            "success": False,
            "error": "NO_ARABIC_BLOCK_FOUND",
            "machine_extracted_text": "",
            "metrics": anchor_metrics(anchor, ""),
            "selected_block": None,
        }
    candidates.sort(key=lambda item: (
        -item["score"],
        len(item["block"]["text"]),
        item["block"]["text"],
    ))
    best = candidates[0]
    return {
        "success": True,
        "error": "",
        "machine_extracted_text": best["block"]["text"],
        "metrics": best["metrics"],
        "selected_block": {
            "tag": best["block"]["tag"],
            "classes": best["block"]["classes"],
            "id": best["block"]["id"],
            "score": best["score"],
        },
    }


def parse_quran_keys(locator: str) -> list[str]:
    match = QURAN_LOCATOR_RE.fullmatch(locator.strip())
    if not match:
        raise RemoteSourceMaterializationError(
            f"Invalid Quran locator: {locator}"
        )
    chapter = int(match.group(1))
    start = int(match.group(2))
    end = int(match.group(3) or start)
    if end < start or end - start > 20:
        raise RemoteSourceMaterializationError(
            f"Invalid Quran range: {locator}"
        )
    return [f"{chapter}:{verse}" for verse in range(start, end + 1)]


def parse_quran_api_response(raw: bytes, verse_key: str) -> str:
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError):
        payload = None
    if isinstance(payload, Mapping):
        verses = payload.get("verses")
        if isinstance(verses, list):
            for verse in verses:
                if not isinstance(verse, Mapping):
                    continue
                if verse.get("verse_key") in (None, verse_key):
                    value = verse.get("text_uthmani")
                    if isinstance(value, str) and value.strip():
                        return value.strip()
        verse = payload.get("verse")
        if isinstance(verse, Mapping):
            value = verse.get("text_uthmani")
            if isinstance(value, str) and value.strip():
                return value.strip()
        data = payload.get("data")
        if isinstance(data, Mapping):
            value = data.get("text")
            if isinstance(value, str) and value.strip():
                return value.strip()
    text = raw.decode("utf-8", errors="replace")
    matches = TEXT_UTHMANI_RE.findall(text)
    for encoded in matches:
        try:
            value = json.loads(encoded)
        except json.JSONDecodeError:
            continue
        if isinstance(value, str) and value.strip():
            return html.unescape(value).strip()
    return ""


def quran_request_urls(verse_key: str) -> list[str]:
    encoded = urllib.parse.quote(verse_key, safe=":")
    return [
        (
            "https://api.quran.com/api/v4/quran/verses/uthmani"
            f"?verse_key={encoded}"
        ),
        (
            "https://api.quran.com/api/v4/verses/by_key/"
            f"{encoded}?fields=text_uthmani"
        ),
        "https://quran.com/" + verse_key.replace(":", "/"),
    ]


def default_fetcher(
    url: str,
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    retries: int = DEFAULT_RETRIES,
) -> dict:
    headers = {
        "User-Agent": (
            "SIRAJ-Source-Materializer/1.0 "
            "(research archive; human verification required)"
        ),
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.5",
        "Accept-Language": "ar,en;q=0.8",
        "Cache-Control": "no-cache",
    }
    errors = []
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(
                request, timeout=timeout_seconds
            ) as response:
                data = response.read(MAX_RESPONSE_BYTES + 1)
                if len(data) > MAX_RESPONSE_BYTES:
                    raise RemoteSourceMaterializationError(
                        f"Response exceeds {MAX_RESPONSE_BYTES} bytes."
                    )
                content_type = response.headers.get(
                    "Content-Type", ""
                )
                charset = response.headers.get_content_charset() or "utf-8"
                return {
                    "success": True,
                    "requested_url": url,
                    "final_url": response.geturl(),
                    "http_status": int(getattr(response, "status", 200)),
                    "content_type": content_type,
                    "charset": charset,
                    "response_bytes": data,
                    "response_bytes_count": len(data),
                    "response_sha256": bytes_sha256(data),
                    "attempt_count": attempt + 1,
                    "errors": errors,
                }
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            OSError,
            RemoteSourceMaterializationError,
        ) as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            if attempt < retries:
                time.sleep(0.7 * (attempt + 1))
    return {
        "success": False,
        "requested_url": url,
        "final_url": "",
        "http_status": 0,
        "content_type": "",
        "charset": "",
        "response_bytes": b"",
        "response_bytes_count": 0,
        "response_sha256": "",
        "attempt_count": retries + 1,
        "errors": errors,
    }


def _materialization_status(
    *, fetched: bool, extracted: bool, metrics: Mapping[str, object]
) -> str:
    if not fetched:
        return "FETCH_FAILED"
    if not extracted:
        return "FETCHED_EXTRACTION_FAILED"
    coverage = float(metrics.get("anchor_token_coverage", 0))
    substring = bool(metrics.get("normalized_anchor_is_substring"))
    if substring or coverage >= 0.82:
        return "FETCHED_EXTRACTED_ANCHOR_MATCH"
    if coverage >= 0.55:
        return "FETCHED_EXTRACTED_PARTIAL_MATCH"
    return "FETCHED_EXTRACTED_ANCHOR_MISMATCH"


def fetch_hadith_candidate(
    source: Mapping[str, object],
    fetcher: Callable[..., dict],
) -> dict:
    retrieval = fetcher(str(source["source_url"]))
    raw = retrieval.pop("response_bytes")
    extraction = (
        choose_hadith_arabic_block(
            raw, str(source["arabic_anchor_text"])
        )
        if retrieval["success"]
        else {
            "success": False,
            "error": "FETCH_FAILED",
            "machine_extracted_text": "",
            "metrics": anchor_metrics(
                str(source["arabic_anchor_text"]), ""
            ),
            "selected_block": None,
        }
    )
    status = _materialization_status(
        fetched=bool(retrieval["success"]),
        extracted=bool(extraction["success"]),
        metrics=extraction["metrics"],
    )
    return {
        "source_candidate_id": source["source_candidate_id"],
        "source_kind": source["source_kind"],
        "locator": source["locator"],
        "status": status,
        "retrievals": [{**retrieval, "raw_bytes": raw}],
        "machine_extracted_text": extraction["machine_extracted_text"],
        "machine_extracted_text_sha256": (
            text_sha256(extraction["machine_extracted_text"])
            if extraction["machine_extracted_text"]
            else ""
        ),
        "anchor_comparison": extraction["metrics"],
        "extraction_details": {
            "parser": "HTML_BLOCK_ARABIC_ANCHOR_SELECTOR_V1",
            "selected_block": extraction["selected_block"],
            "error": extraction["error"],
        },
    }


def fetch_quran_candidate(
    source: Mapping[str, object],
    fetcher: Callable[..., dict],
) -> dict:
    keys = parse_quran_keys(str(source["locator"]))
    retrievals = []
    extracted_verses = []
    errors = []
    for verse_key in keys:
        verse_text = ""
        verse_retrievals = []
        for url in quran_request_urls(verse_key):
            retrieval = fetcher(url)
            raw = retrieval.pop("response_bytes")
            retrieval_record = {
                **retrieval,
                "verse_key": verse_key,
                "raw_bytes": raw,
            }
            verse_retrievals.append(retrieval_record)
            if retrieval["success"]:
                parsed = parse_quran_api_response(raw, verse_key)
                if parsed:
                    verse_text = parsed
                    break
        retrievals.extend(verse_retrievals)
        if verse_text:
            extracted_verses.append({
                "verse_key": verse_key,
                "text_uthmani": verse_text,
                "text_sha256": text_sha256(verse_text),
            })
        else:
            errors.append(f"NO_QURAN_TEXT_EXTRACTED:{verse_key}")
    combined = " | ".join(
        item["text_uthmani"] for item in extracted_verses
    )
    metrics = anchor_metrics(
        str(source["arabic_anchor_text"]), combined
    )
    fetched = any(item["success"] for item in retrievals)
    extracted = len(extracted_verses) == len(keys)
    status = _materialization_status(
        fetched=fetched, extracted=extracted, metrics=metrics
    )
    return {
        "source_candidate_id": source["source_candidate_id"],
        "source_kind": source["source_kind"],
        "locator": source["locator"],
        "status": status,
        "retrievals": retrievals,
        "machine_extracted_text": combined,
        "machine_extracted_text_sha256": (
            text_sha256(combined) if combined else ""
        ),
        "anchor_comparison": metrics,
        "extraction_details": {
            "parser": "QURAN_JSON_OR_EMBEDDED_TEXT_UTHMANI_V1",
            "verse_keys": keys,
            "extracted_verses": extracted_verses,
            "errors": errors,
        },
    }


def fetch_source_candidate(
    source: Mapping[str, object],
    fetcher: Callable[..., dict] = default_fetcher,
) -> dict:
    kind = str(source.get("source_kind", ""))
    if kind == "HADITH_COLLECTION_RECORD":
        return fetch_hadith_candidate(source, fetcher)
    if kind in {"QURAN_VERSE", "QURAN_VERSE_RANGE"}:
        return fetch_quran_candidate(source, fetcher)
    raise RemoteSourceMaterializationError(
        f"Unsupported source kind: {kind}"
    )


def build_policy() -> dict:
    policy = {
        "schema_version": POLICY_SCHEMA,
        "status": "REMOTE_SOURCE_MATERIALIZATION_POLICY_ACTIVE",
        "episode_id": "episode-001-adam",
        "machine_success_statuses": [
            "FETCHED_EXTRACTED_ANCHOR_MATCH",
            "FETCHED_EXTRACTED_PARTIAL_MATCH",
            "FETCHED_EXTRACTED_ANCHOR_MISMATCH",
        ],
        "human_verification_required_fields": [
            "human_compared_to_source",
            "approved_exact_excerpt",
            "approved_context_before_after",
            "source_verified",
            "verified_by",
            "verified_at",
        ],
        "rules": {
            "raw_archive": (
                "Every successful HTTP response is archived locally with "
                "its SHA-256 digest."
            ),
            "machine_extraction": (
                "Machine-extracted text and anchor similarity are preparation "
                "signals, not verified evidence."
            ),
            "quran": (
                "Uthmani text must be human-compared against an authorized "
                "Mushaf source before source_verified."
            ),
            "hadith": (
                "Collection page retrieval does not itself authenticate the "
                "report or resolve variant numbering."
            ),
            "partial_network_failure": (
                "Failures are recorded without silently substituting another "
                "source or asserting completion."
            ),
        },
        "prohibitions": [
            "automatic source verification",
            "automatic human comparison",
            "automatic hadith grading",
            "automatic source authentication",
            "automatic source-origin classification",
            "automatic narration disposition",
            "automatic evidence approval",
            "opening the evidence gate",
            "provider execution",
        ],
        "human_approval": False,
        "source_verification_complete": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    policy["policy_id"] = (
        "adam_remote_materialization_policy_"
        + canonical_sha256(policy)[:16]
    )
    validate_policy(policy)
    return policy


def load_catalog(path: Path) -> dict:
    catalog = read_json(path)
    if not isinstance(catalog, Mapping):
        raise RemoteSourceMaterializationError(
            "Source catalog must be an object."
        )
    if catalog.get("schema_version") != EXPECTED_CATALOG_SCHEMA:
        raise RemoteSourceMaterializationError(
            "Unexpected source catalog schema."
        )
    sources = catalog.get("source_candidates")
    if not isinstance(sources, list) or len(sources) != EXPECTED_SOURCE_COUNT:
        raise RemoteSourceMaterializationError(
            "Expected exactly 22 source candidates."
        )
    if catalog.get("human_approval") is not False:
        raise RemoteSourceMaterializationError(
            "Catalog unexpectedly claims human approval."
        )
    return dict(catalog)


def load_event_pack(path: Path) -> dict:
    pack = read_json(path)
    if not isinstance(pack, Mapping):
        raise RemoteSourceMaterializationError(
            "Event/source pack must be an object."
        )
    if pack.get("schema_version") != EXPECTED_PACK_SCHEMA:
        raise RemoteSourceMaterializationError(
            "Unexpected event/source pack schema."
        )
    if pack.get("event_count") != EXPECTED_EVENT_COUNT:
        raise RemoteSourceMaterializationError(
            "Expected fourteen factual events."
        )
    if pack.get("event_source_link_count") != EXPECTED_LINK_COUNT:
        raise RemoteSourceMaterializationError(
            "Expected 28 event/source links."
        )
    return dict(pack)


def build_review_template(
    catalog: Mapping[str, object],
    policy: Mapping[str, object],
    *,
    materialization_id: str = "PENDING_LOCAL_NETWORK_RUN",
    materialization_sha256: str = "0" * 64,
) -> dict:
    review = {
        "schema_version": REVIEW_SCHEMA,
        "status": "TEMPLATE_NOT_APPROVED",
        "episode_id": "episode-001-adam",
        "materialization_id": materialization_id,
        "materialization_sha256": materialization_sha256,
        "policy_id": policy["policy_id"],
        "policy_sha256": canonical_sha256(policy),
        "source_count": catalog["source_candidate_count"],
        "decisions": [
            {
                "source_candidate_id": item["source_candidate_id"],
                "locator": item["locator"],
                "machine_materialization_status": "",
                "machine_extracted_text_sha256": "",
                "human_compared_to_source": False,
                "approved_exact_excerpt": "",
                "approved_context_before_after": "",
                "source_verified": False,
                "authentication_verified": False,
                "origin_classification_verified": False,
                "approved": False,
                "human_decision": False,
                "verified_by": "",
                "verified_at": "",
                "reviewer_notes": "",
            }
            for item in catalog["source_candidates"]
        ],
        "approved_by": "",
        "approved_at": "",
        "human_approval": False,
        "source_verification_complete": False,
        "full_episode_adjudication_complete": False,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    validate_review_template(review)
    return review


def _strip_raw_bytes(materialization: Mapping[str, object]) -> dict:
    clean = dict(materialization)
    clean["retrievals"] = [
        {
            key: value
            for key, value in retrieval.items()
            if key != "raw_bytes"
        }
        for retrieval in materialization["retrievals"]
    ]
    return clean


def build_materialization(
    *,
    catalog: Mapping[str, object],
    event_pack: Mapping[str, object],
    policy: Mapping[str, object],
    fetcher: Callable[..., dict] = default_fetcher,
    max_workers: int = 6,
) -> tuple[dict, dict, dict[str, bytes], dict]:
    source_list = list(catalog["source_candidates"])
    results_by_id: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, min(max_workers, 8))
    ) as executor:
        future_map = {
            executor.submit(fetch_source_candidate, source, fetcher):
            source["source_candidate_id"]
            for source in source_list
        }
        for future in concurrent.futures.as_completed(future_map):
            source_id = future_map[future]
            try:
                results_by_id[source_id] = future.result()
            except Exception as exc:  # recorded, never silently swallowed
                source = next(
                    item for item in source_list
                    if item["source_candidate_id"] == source_id
                )
                results_by_id[source_id] = {
                    "source_candidate_id": source_id,
                    "source_kind": source["source_kind"],
                    "locator": source["locator"],
                    "status": "FETCH_FAILED",
                    "retrievals": [],
                    "machine_extracted_text": "",
                    "machine_extracted_text_sha256": "",
                    "anchor_comparison": anchor_metrics(
                        source["arabic_anchor_text"], ""
                    ),
                    "extraction_details": {
                        "parser": "",
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                }

    raw_files: dict[str, bytes] = {}
    materialized_sources = []
    fetch_records = []
    source_index = {
        item["source_candidate_id"]: item
        for item in source_list
    }
    for source in source_list:
        source_id = source["source_candidate_id"]
        result = results_by_id[source_id]
        retrieval_refs = []
        for index, retrieval in enumerate(result["retrievals"], 1):
            raw = retrieval.get("raw_bytes", b"")
            raw_path = ""
            if raw:
                suffix = ".json" if "json" in str(
                    retrieval.get("content_type", "")
                ).lower() else ".html"
                raw_path = (
                    f"raw/{source_id}/{index:02d}-response{suffix}"
                )
                raw_files[raw_path] = raw
            clean = {
                key: value
                for key, value in retrieval.items()
                if key != "raw_bytes"
            }
            clean["raw_archive_path"] = raw_path
            retrieval_refs.append(clean)
            fetch_records.append({
                "source_candidate_id": source_id,
                **clean,
            })

        materialized = {
            "source_candidate_id": source_id,
            "candidate_record_id": source["candidate_record_id"],
            "source_kind": source["source_kind"],
            "collection": source["collection"],
            "locator": source["locator"],
            "source_url": source["source_url"],
            "research_anchor_text": source["arabic_anchor_text"],
            "research_anchor_sha256": source["arabic_anchor_sha256"],
            "materialization_status": result["status"],
            "retrievals": retrieval_refs,
            "response_archive_count": sum(
                bool(item["raw_archive_path"]) for item in retrieval_refs
            ),
            "combined_response_sha256": canonical_sha256([
                item["response_sha256"]
                for item in retrieval_refs
                if item["response_sha256"]
            ]),
            "machine_extracted_text": result[
                "machine_extracted_text"
            ],
            "machine_extracted_text_sha256": result[
                "machine_extracted_text_sha256"
            ],
            "anchor_comparison": result["anchor_comparison"],
            "extraction_details": result["extraction_details"],
            "machine_materialized": bool(
                result["machine_extracted_text"]
            ),
            "human_compared_to_source": False,
            "source_verified": False,
            "authentication_verified": False,
            "origin_classification_verified": False,
            "human_decision": False,
            "approved_for_event_binding": False,
        }
        materialized["materialization_record_id"] = (
            "remote_materialization_"
            + canonical_sha256(materialized)[:16]
        )
        materialized_sources.append(materialized)

    status_counts = dict(sorted(Counter(
        item["materialization_status"]
        for item in materialized_sources
    ).items()))
    fetched_count = sum(
        any(retrieval["success"] for retrieval in item["retrievals"])
        for item in materialized_sources
    )
    extracted_count = sum(
        bool(item["machine_extracted_text"])
        for item in materialized_sources
    )
    anchor_match_count = sum(
        item["materialization_status"]
        == "FETCHED_EXTRACTED_ANCHOR_MATCH"
        for item in materialized_sources
    )
    materialization = {
        "schema_version": MATERIALIZATION_SCHEMA,
        "status": STATUS,
        "episode_id": "episode-001-adam",
        "catalog_id": catalog["catalog_id"],
        "catalog_sha256": canonical_sha256(catalog),
        "event_pack_id": event_pack["pack_id"],
        "event_pack_sha256": canonical_sha256(event_pack),
        "policy_id": policy["policy_id"],
        "policy_sha256": canonical_sha256(policy),
        "source_count": len(materialized_sources),
        "fetched_source_count": fetched_count,
        "machine_extracted_source_count": extracted_count,
        "anchor_match_source_count": anchor_match_count,
        "status_counts": status_counts,
        "sources": materialized_sources,
        "human_approval": False,
        "source_verification_complete": False,
        "full_episode_adjudication_complete": False,
        "approved_evidence_package_complete": False,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    materialization["materialization_id"] = (
        "adam_remote_source_materialization_"
        + canonical_sha256(materialization)[:16]
    )

    fetch_manifest = {
        "schema_version": FETCH_SCHEMA,
        "status": "REMOTE_FETCH_MANIFEST_COMPLETE",
        "episode_id": "episode-001-adam",
        "materialization_id": materialization["materialization_id"],
        "fetch_request_count": len(fetch_records),
        "successful_response_count": sum(
            item["success"] for item in fetch_records
        ),
        "archived_response_count": len(raw_files),
        "records": fetch_records,
        "human_approval": False,
        "source_verification_complete": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }

    source_materialization_index = {
        item["source_candidate_id"]: item
        for item in materialized_sources
    }
    prefill_items = []
    for event in event_pack["events"]:
        for source_id in event["source_candidate_ids"]:
            materialized = source_materialization_index[source_id]
            prefill_items.append({
                "event_id": event["event_id"],
                "event_title": event["title"],
                "proposed_disposition": event[
                    "proposed_disposition"
                ],
                "source_candidate_id": source_id,
                "materialization_record_id": materialized[
                    "materialization_record_id"
                ],
                "materialization_status": materialized[
                    "materialization_status"
                ],
                "suggested_machine_excerpt": materialized[
                    "machine_extracted_text"
                ],
                "suggested_machine_excerpt_sha256": materialized[
                    "machine_extracted_text_sha256"
                ],
                "copy_into_verified_exact_excerpt": False,
                "human_comparison_required": True,
                "source_verified": False,
                "human_decision": False,
            })
    prefill = {
        "schema_version": PREFILL_SCHEMA,
        "status": "PREFILL_SUGGESTIONS_HUMAN_COMPARISON_REQUIRED",
        "episode_id": "episode-001-adam",
        "materialization_id": materialization["materialization_id"],
        "event_source_suggestion_count": len(prefill_items),
        "suggestions": prefill_items,
        "human_approval": False,
        "source_verification_complete": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }

    validate_materialization(materialization)
    validate_fetch_manifest(fetch_manifest)
    validate_prefill(prefill)
    return materialization, fetch_manifest, raw_files, prefill


def build_event_readiness(
    materialization: Mapping[str, object],
    event_pack: Mapping[str, object],
) -> dict:
    source_index = {
        item["source_candidate_id"]: item
        for item in materialization["sources"]
    }
    events = []
    for event in event_pack["events"]:
        sources = [
            source_index[source_id]
            for source_id in event["source_candidate_ids"]
        ]
        statuses = Counter(
            item["materialization_status"] for item in sources
        )
        events.append({
            "event_id": event["event_id"],
            "title": event["title"],
            "proposed_disposition": event["proposed_disposition"],
            "source_candidate_count": len(sources),
            "machine_extracted_source_count": sum(
                bool(item["machine_extracted_text"]) for item in sources
            ),
            "anchor_match_source_count": sum(
                item["materialization_status"]
                == "FETCHED_EXTRACTED_ANCHOR_MATCH"
                for item in sources
            ),
            "source_status_counts": dict(sorted(statuses.items())),
            "human_source_comparison_required": True,
            "source_verification_complete": False,
            "event_approved": False,
        })
    return {
        "schema_version": "siraj-remote-source-event-readiness-v1",
        "materialization_id": materialization["materialization_id"],
        "event_count": len(events),
        "events": events,
        "source_verification_complete": False,
        "human_approval": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }


def validate_policy(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != POLICY_SCHEMA:
        raise RemoteSourceMaterializationError(
            "Unexpected policy schema."
        )
    if "automatic source verification" not in data.get(
        "prohibitions", []
    ):
        raise RemoteSourceMaterializationError(
            "Automatic-verification prohibition missing."
        )
    if data.get("source_verification_complete") is not False:
        raise RemoteSourceMaterializationError(
            "Policy cannot complete verification."
        )
    _validate_guards(data)


def validate_review_template(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != REVIEW_SCHEMA:
        raise RemoteSourceMaterializationError(
            "Unexpected review schema."
        )
    if data.get("status") != "TEMPLATE_NOT_APPROVED":
        raise RemoteSourceMaterializationError(
            "Review template cannot be approved."
        )
    decisions = data.get("decisions")
    if not isinstance(decisions, list) or len(decisions) != 22:
        raise RemoteSourceMaterializationError(
            "Review template must cover 22 sources."
        )
    for item in decisions:
        blank_fields = (
            "machine_materialization_status",
            "machine_extracted_text_sha256",
            "approved_exact_excerpt",
            "approved_context_before_after",
            "verified_by", "verified_at", "reviewer_notes",
        )
        if any(item.get(field) for field in blank_fields):
            raise RemoteSourceMaterializationError(
                "Tracked review template must remain blank."
            )
        false_fields = (
            "human_compared_to_source", "source_verified",
            "authentication_verified",
            "origin_classification_verified", "approved",
            "human_decision",
        )
        if any(item.get(field) is not False for field in false_fields):
            raise RemoteSourceMaterializationError(
                "Review template cannot claim verification."
            )
    if data.get("approved_by") or data.get("approved_at"):
        raise RemoteSourceMaterializationError(
            "Reviewer metadata must remain blank."
        )
    _validate_guards(data)


def validate_materialization(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != MATERIALIZATION_SCHEMA:
        raise RemoteSourceMaterializationError(
            "Unexpected materialization schema."
        )
    if data.get("status") != STATUS:
        raise RemoteSourceMaterializationError(
            "Unexpected materialization status."
        )
    sources = data.get("sources")
    if not isinstance(sources, list) or len(sources) != 22:
        raise RemoteSourceMaterializationError(
            "Materialization must cover 22 sources."
        )
    ids = [item["source_candidate_id"] for item in sources]
    if len(ids) != len(set(ids)):
        raise RemoteSourceMaterializationError(
            "Materialization source ids are duplicated."
        )
    for item in sources:
        extracted = item.get("machine_extracted_text", "")
        extracted_sha = item.get(
            "machine_extracted_text_sha256", ""
        )
        if extracted:
            if text_sha256(extracted) != extracted_sha:
                raise RemoteSourceMaterializationError(
                    "Machine-extracted checksum mismatch."
                )
        elif extracted_sha:
            raise RemoteSourceMaterializationError(
                "Empty extraction cannot have checksum."
            )
        for retrieval in item["retrievals"]:
            if "raw_bytes" in retrieval:
                raise RemoteSourceMaterializationError(
                    "Raw bytes cannot enter JSON materialization."
                )
            if retrieval.get("success"):
                digest = retrieval.get("response_sha256", "")
                if not re.fullmatch(r"[0-9a-f]{64}", digest):
                    raise RemoteSourceMaterializationError(
                        "Successful response checksum invalid."
                    )
        false_fields = (
            "human_compared_to_source", "source_verified",
            "authentication_verified",
            "origin_classification_verified", "human_decision",
            "approved_for_event_binding",
        )
        if any(item.get(field) is not False for field in false_fields):
            raise RemoteSourceMaterializationError(
                "Materialization cannot claim verification."
            )
    if data.get("source_verification_complete") is not False:
        raise RemoteSourceMaterializationError(
            "Materialization cannot complete verification."
        )
    if data.get("opens_evidence_gate") is not False:
        raise RemoteSourceMaterializationError(
            "Materialization cannot open the gate."
        )
    _validate_guards(data)


def validate_fetch_manifest(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != FETCH_SCHEMA:
        raise RemoteSourceMaterializationError(
            "Unexpected fetch-manifest schema."
        )
    records = data.get("records")
    if not isinstance(records, list):
        raise RemoteSourceMaterializationError(
            "Fetch records missing."
        )
    for item in records:
        if "raw_bytes" in item:
            raise RemoteSourceMaterializationError(
                "Fetch manifest cannot retain raw bytes."
            )
        if item.get("success"):
            if not item.get("raw_archive_path"):
                raise RemoteSourceMaterializationError(
                    "Successful response must be archived."
                )
            if not re.fullmatch(
                r"[0-9a-f]{64}",
                str(item.get("response_sha256", "")),
            ):
                raise RemoteSourceMaterializationError(
                    "Fetch response checksum invalid."
                )
    if data.get("source_verification_complete") is not False:
        raise RemoteSourceMaterializationError(
            "Fetch manifest cannot verify sources."
        )
    _validate_guards(data)


def validate_prefill(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != PREFILL_SCHEMA:
        raise RemoteSourceMaterializationError(
            "Unexpected prefill schema."
        )
    suggestions = data.get("suggestions")
    if not isinstance(suggestions, list) or len(suggestions) != 28:
        raise RemoteSourceMaterializationError(
            "Expected 28 event/source suggestions."
        )
    for item in suggestions:
        if item.get("copy_into_verified_exact_excerpt") is not False:
            raise RemoteSourceMaterializationError(
                "Prefill cannot copy itself into verified evidence."
            )
        if item.get("human_comparison_required") is not True:
            raise RemoteSourceMaterializationError(
                "Human comparison must remain required."
            )
        if item.get("source_verified") is not False:
            raise RemoteSourceMaterializationError(
                "Prefill cannot verify sources."
            )
        if item.get("human_decision") is not False:
            raise RemoteSourceMaterializationError(
                "Prefill cannot record decisions."
            )
    _validate_guards(data)


def _validate_guards(data: Mapping[str, object]) -> None:
    if data.get("human_approval") not in (None, False):
        raise RemoteSourceMaterializationError(
            "Artifact cannot claim human approval."
        )
    if data.get("evidence_gate_status") != GATE:
        raise RemoteSourceMaterializationError(
            "Evidence gate must remain withheld."
        )
    if data.get("automatic_evidence_approval") != AUTO_APPROVAL:
        raise RemoteSourceMaterializationError(
            "Automatic approval must remain forbidden."
        )
    if data.get("live_provider_execution") != LIVE_EXECUTION:
        raise RemoteSourceMaterializationError(
            "Provider execution must remain blocked."
        )


def write_local_outputs(
    *,
    output_root: Path,
    materialization: Mapping[str, object],
    fetch_manifest: Mapping[str, object],
    raw_files: Mapping[str, bytes],
    prefill: Mapping[str, object],
    policy: Mapping[str, object],
    review: Mapping[str, object],
    event_readiness: Mapping[str, object],
) -> dict[str, Path]:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    outputs = {
        "materialization": output_root / (
            "remote-source-materialization-v1.json"
        ),
        "fetch_manifest": output_root / (
            "remote-source-fetch-manifest-v1.json"
        ),
        "prefill": output_root / (
            "remote-source-prefill-suggestion-pack-v1.json"
        ),
        "policy": output_root / (
            "remote-source-materialization-policy-v1.json"
        ),
        "review": output_root / (
            "remote-source-human-review-v1.template.json"
        ),
        "readiness": output_root / (
            "remote-source-event-readiness-v1.json"
        ),
        "coverage_csv": output_root / (
            "remote-source-materialization-coverage.csv"
        ),
        "failure_csv": output_root / (
            "remote-source-fetch-failures.csv"
        ),
        "summary": output_root / "README.md",
    }
    write_json(outputs["materialization"], materialization)
    write_json(outputs["fetch_manifest"], fetch_manifest)
    write_json(outputs["prefill"], prefill)
    write_json(outputs["policy"], policy)
    write_json(outputs["review"], review)
    write_json(outputs["readiness"], event_readiness)

    for relative, raw in raw_files.items():
        path = output_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    extracted_root = output_root / "extracted"
    for source in materialization["sources"]:
        write_json(
            extracted_root / (
                source["source_candidate_id"] + ".json"
            ),
            {
                "source_candidate_id": source[
                    "source_candidate_id"
                ],
                "locator": source["locator"],
                "materialization_status": source[
                    "materialization_status"
                ],
                "machine_extracted_text": source[
                    "machine_extracted_text"
                ],
                "machine_extracted_text_sha256": source[
                    "machine_extracted_text_sha256"
                ],
                "anchor_comparison": source[
                    "anchor_comparison"
                ],
                "extraction_details": source[
                    "extraction_details"
                ],
                "human_compared_to_source": False,
                "source_verified": False,
            },
        )

    fields = (
        "source_candidate_id", "source_kind", "locator",
        "materialization_status", "response_archive_count",
        "machine_materialized", "anchor_token_coverage",
        "normalized_anchor_is_substring",
        "human_compared_to_source", "source_verified",
    )
    with outputs["coverage_csv"].open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for source in materialization["sources"]:
            metrics = source["anchor_comparison"]
            writer.writerow({
                "source_candidate_id": source[
                    "source_candidate_id"
                ],
                "source_kind": source["source_kind"],
                "locator": source["locator"],
                "materialization_status": source[
                    "materialization_status"
                ],
                "response_archive_count": source[
                    "response_archive_count"
                ],
                "machine_materialized": source[
                    "machine_materialized"
                ],
                "anchor_token_coverage": metrics[
                    "anchor_token_coverage"
                ],
                "normalized_anchor_is_substring": metrics[
                    "normalized_anchor_is_substring"
                ],
                "human_compared_to_source": False,
                "source_verified": False,
            })

    failure_fields = (
        "source_candidate_id", "requested_url", "http_status",
        "attempt_count", "errors",
    )
    with outputs["failure_csv"].open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=failure_fields)
        writer.writeheader()
        for item in fetch_manifest["records"]:
            if item["success"]:
                continue
            writer.writerow({
                "source_candidate_id": item[
                    "source_candidate_id"
                ],
                "requested_url": item["requested_url"],
                "http_status": item["http_status"],
                "attempt_count": item["attempt_count"],
                "errors": "; ".join(item["errors"]),
            })

    dossier_root = output_root / "source-dossiers"
    dossier_root.mkdir(parents=True, exist_ok=True)
    for source in materialization["sources"]:
        metrics = source["anchor_comparison"]
        lines = [
            f"# {source['source_candidate_id']}",
            "",
            f"- Locator: `{source['locator']}`",
            f"- Status: `{source['materialization_status']}`",
            f"- Archived responses: {source['response_archive_count']}",
            f"- Anchor token coverage: {metrics['anchor_token_coverage']}",
            f"- Anchor substring: {metrics['normalized_anchor_is_substring']}",
            "- Human compared: no",
            "- Source verified: no",
            "",
            "## Research anchor",
            "",
            "```text",
            source["research_anchor_text"],
            "```",
            "",
            "## Machine-extracted text",
            "",
            "```text",
            source["machine_extracted_text"]
            or "[no machine extraction]",
            "```",
            "",
            "## Human review action",
            "",
            "Open the archived response or authorized source, compare the "
            "exact text and context, then fill the review template. Do not "
            "promote this machine extraction directly to verified evidence.",
            "",
        ]
        (dossier_root / (
            source["source_candidate_id"] + ".md"
        )).write_text(
            "\n".join(lines), encoding="utf-8", newline="\n"
        )

    outputs["summary"].write_text(
        "# Adam Remote Source Materialization v1\n\n"
        f"- Source candidates: {materialization['source_count']}\n"
        f"- Sources with at least one fetched response: "
        f"{materialization['fetched_source_count']}\n"
        f"- Sources with machine-extracted text: "
        f"{materialization['machine_extracted_source_count']}\n"
        f"- Strong anchor matches: "
        f"{materialization['anchor_match_source_count']}\n"
        f"- Archived HTTP responses: "
        f"{fetch_manifest['archived_response_count']}\n"
        f"- Status counts: "
        f"{json.dumps(materialization['status_counts'], ensure_ascii=False, sort_keys=True)}\n"
        "- Machine extraction is not human source verification.\n"
        "- No hadith was graded or authenticated.\n"
        "- Evidence gate remains withheld.\n",
        encoding="utf-8",
        newline="\n",
    )

    archive = output_root.with_suffix(".zip")
    with zipfile.ZipFile(
        archive, "w", zipfile.ZIP_DEFLATED
    ) as bundle:
        for path in sorted(output_root.rglob("*")):
            if path.is_file():
                bundle.write(
                    path, path.relative_to(output_root).as_posix()
                )
    outputs["archive"] = archive
    return outputs
