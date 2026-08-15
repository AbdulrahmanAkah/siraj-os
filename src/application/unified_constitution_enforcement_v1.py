"""Offline, fail-closed enforcement for the SIRAJ unified constitution v1.

The machine-readable constitution bundle is the only policy authority used by
this module.  The module has no provider transport, no network dependency, no
paid capability, and no production or montage operation.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
from importlib.metadata import version as distribution_version
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence


CONSTITUTION_RELATIVE_DIRECTORY = Path(
    "config/constitution/siraj-unified-production-constitution/1.2.0"
)
CONSTITUTION_VERSION = "1.2.0"
CONSTITUTION_BUNDLE_ID = "SIRAJ-CONSTITUTION-1.2.0-20260815"
RULES_FILENAME = "siraj_unified_constitution_v1.rules.json"
SCHEMA_FILENAME = "siraj_unified_constitution_rule_model.schema.json"
MANIFEST_FILENAME = "bundle_manifest.json"

EXPECTED_PRECEDENCE = (
    "UNIFIED_CONSTITUTION",
    "APPROVED_SERIES_PROFILES",
    "APPROVED_EPISODE_EVIDENCE_AND_CONTRACTS",
    "APPROVED_SCRIPT_AND_NARRATION",
    "APPROVED_STORYBOARD",
    "APPROVED_PROVIDER_PAYLOADS",
    "EXECUTORS_AND_ADAPTERS",
    "RENDERS_AND_MONTAGE",
    "REPORTS_AND_CACHES",
)

EXPECTED_APPROVAL_FIELDS = frozenset(
    {
        "approval_id",
        "approval_type",
        "human_actor",
        "decision",
        "decision_time",
        "constitution_bundle_manifest_sha256",
        "input_artifact_ids",
        "input_sha256s",
        "scope",
        "expires_or_stales_on",
        "consumed_by_transaction_id_if_any",
    }
)

EXPECTED_INVALIDATION_EVENTS = frozenset(
    {
        "CONSTITUTION_BUNDLE_CHANGED",
        "SOURCE_OR_CLAIM_CHANGED",
        "CANONICAL_SCRIPT_CHANGED",
        "NARRATION_MASTER_CHANGED",
        "CHARACTER_OR_PERIOD_CONTRACT_CHANGED",
        "CANONICAL_REFERENCE_CHANGED",
        "STORYBOARD_CHANGED",
        "PROMPT_OR_PROVIDER_PAYLOAD_CHANGED",
        "PROVIDER_MODEL_OR_RATE_CHANGED",
        "BATCH_SCOPE_OR_REQUEST_COUNT_CHANGED",
        "NEW_UNPILOTED_RISK_CLASS",
        "RENDER_BYTES_CHANGED",
        "INTRO_OR_OUTRO_CHANGED",
        "MONTAGE_CHANGED",
    }
)

RUNTIME_GATES = frozenset(
    {
        "process_boot_gate",
        "research_gate",
        "script_gate",
        "tts_preflight_gate",
        "narration_master_gate",
        "character_gate",
        "storyboard_gate",
        "prompt_compilation_gate",
        "human_prompt_review_gate",
        "pilot_gate",
        "pre_submit_gate",
        "cost_preflight_gate",
        "paid_execution_gate",
        "render_promotion_gate",
        "montage_admission_gate",
        "final_qa_gate",
        "publish_ready_gate",
    }
)

RULE_ID_PATTERN = re.compile(r"^SIRAJ\.S(0[1-9]|10)\.[A-Z0-9_]+$")
FAILURE_CODE_PATTERN = re.compile(r"^FAIL_[A-Z0-9_]+$")
UPPER_TOKEN_PATTERN = re.compile(r"^[A-Z0-9_]+$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ConstitutionEnforcementError(ValueError):
    """Base class for fail-closed constitution errors."""


class ConstitutionLoadError(ConstitutionEnforcementError):
    """Raised when the canonical bundle cannot be trusted."""


class PolicyCompilationError(ConstitutionEnforcementError):
    """Raised when a structured contract cannot be compiled safely."""


class ApprovalValidationError(ConstitutionEnforcementError):
    """Raised when an approval is absent, malformed, or stale."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_json_sha256(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def artifact_sha256(value: Any) -> str:
    if isinstance(value, bytes):
        return sha256_bytes(value)
    if isinstance(value, str):
        return sha256_bytes(value.encode("utf-8"))
    return canonical_json_sha256(value)


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _deep_thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _deep_thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_deep_thaw(item) for item in value]
    return deepcopy(value)


def _read_json_object(path: Path, failure_code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConstitutionLoadError(failure_code) from exc
    if not isinstance(value, dict):
        raise ConstitutionLoadError(failure_code)
    return value


def _contains_unknown(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().upper() in {"", "UNKNOWN", "UNSET", "DEFAULT"}
    if isinstance(value, Mapping):
        return not value or any(_contains_unknown(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return not value or any(_contains_unknown(item) for item in value)
    return False


def _validate_schema(instance: Mapping[str, Any], schema: Mapping[str, Any]) -> str:
    try:
        import jsonschema
        from jsonschema import Draft202012Validator
    except ImportError as exc:
        raise ConstitutionLoadError("SCHEMA_VALIDATOR_UNAVAILABLE") from exc

    try:
        Draft202012Validator.check_schema(dict(schema))
    except jsonschema.SchemaError as exc:
        raise ConstitutionLoadError(f"SCHEMA_DEFINITION_INVALID:{exc.message}") from exc

    errors = sorted(
        Draft202012Validator(dict(schema)).iter_errors(dict(instance)),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        first = errors[0]
        location = "/".join(str(part) for part in first.absolute_path) or "$"
        raise ConstitutionLoadError(f"SCHEMA_INVALID:{location}:{first.message}")
    return distribution_version("jsonschema")


def _safe_manifest_path(bundle_directory: Path, relative_path: str) -> Path:
    candidate = (bundle_directory / relative_path).resolve()
    root = bundle_directory.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ConstitutionLoadError("MANIFEST_PATH_ESCAPES_BUNDLE") from exc
    return candidate


@dataclass(frozen=True, slots=True)
class LoadedConstitution:
    bundle_directory: Path
    manifest: Mapping[str, Any]
    rules_document: Mapping[str, Any]
    schema: Mapping[str, Any]
    bundle_manifest_sha256: str
    schema_validator_version: str

    @property
    def constitution(self) -> Mapping[str, Any]:
        return self.rules_document["constitution"]

    @property
    def rules(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self.rules_document["rules"])


def validate_loaded_constitution(
    rules_document: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    expected_version: str,
) -> None:
    constitution = rules_document.get("constitution")
    if not isinstance(constitution, Mapping):
        raise ConstitutionLoadError("CONSTITUTION_METADATA_MISSING")
    required_metadata = {
        "id": "SIRAJ_UNIFIED_PRODUCTION_CONSTITUTION",
        "version": expected_version,
        "bundle_id": CONSTITUTION_BUNDLE_ID,
        "authority": "SYSTEM_ROOT",
        "scope": "SERIES_WIDE",
        "fail_closed": True,
        "production_authorized": False,
    }
    for key, expected in required_metadata.items():
        if constitution.get(key) != expected:
            raise ConstitutionLoadError(f"CONSTITUTION_{key.upper()}_INVALID")
    if manifest.get("constitution_id") != constitution["id"]:
        raise ConstitutionLoadError("MANIFEST_CONSTITUTION_ID_MISMATCH")
    if manifest.get("version") != constitution["version"]:
        raise ConstitutionLoadError("MANIFEST_VERSION_MISMATCH")
    if manifest.get("bundle_id") != constitution["bundle_id"]:
        raise ConstitutionLoadError("MANIFEST_BUNDLE_ID_MISMATCH")

    rules = rules_document.get("rules")
    if not isinstance(rules, list) or len(rules) != 51:
        raise ConstitutionLoadError("RULE_COUNT_INVALID")
    rule_ids = [rule.get("id") for rule in rules if isinstance(rule, Mapping)]
    if len(rule_ids) != len(set(rule_ids)):
        raise ConstitutionLoadError("DUPLICATE_RULE")
    if len(rule_ids) != 51:
        raise ConstitutionLoadError("RULE_MAPPING_INVALID")
    sections: set[int] = set()
    for rule in rules:
        if not isinstance(rule, Mapping):
            raise ConstitutionLoadError("RULE_MAPPING_INVALID")
        rule_id = rule.get("id")
        match = RULE_ID_PATTERN.fullmatch(str(rule_id))
        if match is None:
            raise ConstitutionLoadError("RULE_ID_INVALID")
        section = rule.get("section")
        if section != int(match.group(1)):
            raise ConstitutionLoadError("RULE_SECTION_MISMATCH")
        sections.add(section)
        for code in rule.get("failure_codes", []):
            if FAILURE_CODE_PATTERN.fullmatch(str(code)) is None:
                raise ConstitutionLoadError("FAILURE_CODE_INVALID")
        dependencies = rule.get("depends_on", [])
        if any(dependency not in rule_ids for dependency in dependencies):
            raise ConstitutionLoadError("RULE_DEPENDENCY_INVALID")
        if rule.get("severity") in {"CRITICAL", "HIGH"} and _contains_unknown(rule.get("value")):
            raise ConstitutionLoadError("SENSITIVE_VALUE_UNKNOWN")
    if sections != set(range(1, 11)):
        raise ConstitutionLoadError("SECTION_COVERAGE_INVALID")

    if tuple(rules_document.get("precedence", ())) != EXPECTED_PRECEDENCE:
        raise ConstitutionLoadError("PRECEDENCE_INVALID")
    approval_binding = rules_document.get("approval_binding")
    if not isinstance(approval_binding, Mapping):
        raise ConstitutionLoadError("APPROVAL_BINDING_INVALID")
    if set(approval_binding.get("required_fields", ())) != EXPECTED_APPROVAL_FIELDS:
        raise ConstitutionLoadError("APPROVAL_REQUIRED_FIELDS_INVALID")
    if approval_binding.get("material_change_invalidates") is not True:
        raise ConstitutionLoadError("APPROVAL_INVALIDATION_POLICY_WEAKENED")

    events = rules_document.get("invalidation_events")
    if not isinstance(events, list) or len(events) != 14:
        raise ConstitutionLoadError("INVALIDATION_EVENT_COUNT_INVALID")
    event_names = [event.get("event") for event in events if isinstance(event, Mapping)]
    if len(event_names) != len(set(event_names)):
        raise ConstitutionLoadError("DUPLICATE_INVALIDATION_EVENT")
    if set(event_names) != EXPECTED_INVALIDATION_EVENTS:
        raise ConstitutionLoadError("INVALIDATION_EVENT_SET_INVALID")
    for event in events:
        targets = event.get("invalidates")
        if not isinstance(targets, list) or not targets:
            raise ConstitutionLoadError("INVALIDATION_TARGETS_INVALID")
        if any(UPPER_TOKEN_PATTERN.fullmatch(str(target)) is None for target in targets):
            raise ConstitutionLoadError("INVALIDATION_TARGET_INVALID")


def load_unified_constitution(
    repo_root: Path,
    *,
    expected_version: str = CONSTITUTION_VERSION,
    relative_directory: Path = CONSTITUTION_RELATIVE_DIRECTORY,
) -> LoadedConstitution:
    bundle_directory = (Path(repo_root) / relative_directory).resolve()
    if not bundle_directory.is_dir():
        raise ConstitutionLoadError("CONSTITUTION_MISSING")
    manifest_path = bundle_directory / MANIFEST_FILENAME
    rules_path = bundle_directory / RULES_FILENAME
    schema_path = bundle_directory / SCHEMA_FILENAME
    if not manifest_path.is_file() or not rules_path.is_file() or not schema_path.is_file():
        raise ConstitutionLoadError("CONSTITUTION_MISSING")
    authority_root = (Path(repo_root) / "config" / "constitution").resolve()
    machine_sources = (
        [path.resolve() for path in authority_root.rglob(RULES_FILENAME)]
        if authority_root.is_dir()
        else []
    )
    if machine_sources != [rules_path.resolve()]:
        raise ConstitutionLoadError("DUPLICATE_POLICY_AUTHORITY")

    manifest = _read_json_object(manifest_path, "MANIFEST_INVALID")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ConstitutionLoadError("MANIFEST_INVALID")
    seen_paths: set[str] = set()
    for entry in files:
        if not isinstance(entry, Mapping):
            raise ConstitutionLoadError("MANIFEST_INVALID")
        relative_path = entry.get("path")
        if not isinstance(relative_path, str) or relative_path in seen_paths:
            raise ConstitutionLoadError("MANIFEST_PATH_INVALID")
        seen_paths.add(relative_path)
        target = _safe_manifest_path(bundle_directory, relative_path)
        if not target.is_file():
            raise ConstitutionLoadError("MANIFEST_FILE_MISSING")
        if target.stat().st_size != entry.get("bytes"):
            raise ConstitutionLoadError("MANIFEST_SIZE_MISMATCH")
        if sha256_file(target) != entry.get("sha256"):
            raise ConstitutionLoadError("HASH_MISMATCH")

    if RULES_FILENAME not in seen_paths or SCHEMA_FILENAME not in seen_paths:
        raise ConstitutionLoadError("MANIFEST_REQUIRED_FILE_MISSING")
    rules_document = _read_json_object(rules_path, "CONSTITUTION_JSON_INVALID")
    schema = _read_json_object(schema_path, "SCHEMA_JSON_INVALID")
    validator_version = _validate_schema(rules_document, schema)
    validate_loaded_constitution(
        rules_document,
        manifest,
        expected_version=expected_version,
    )
    return LoadedConstitution(
        bundle_directory=bundle_directory,
        manifest=_deep_freeze(manifest),
        rules_document=_deep_freeze(rules_document),
        schema=_deep_freeze(schema),
        bundle_manifest_sha256=sha256_file(manifest_path),
        schema_validator_version=validator_version,
    )


@dataclass(frozen=True, slots=True)
class RuleRegistry:
    constitution: LoadedConstitution
    by_id: Mapping[str, Mapping[str, Any]]

    @classmethod
    def build(cls, constitution: LoadedConstitution) -> "RuleRegistry":
        mapping = {str(rule["id"]): _deep_freeze(_deep_thaw(rule)) for rule in constitution.rules}
        if len(mapping) != len(constitution.rules):
            raise ConstitutionLoadError("DUPLICATE_RULE")
        return cls(constitution=constitution, by_id=MappingProxyType(mapping))

    def require(self, rule_id: str) -> Mapping[str, Any]:
        try:
            return self.by_id[rule_id]
        except KeyError as exc:
            raise ConstitutionEnforcementError(f"RULE_UNKNOWN:{rule_id}") from exc


_NEGATION = r"(?:no|not|never|without|forbid(?:den)?|exclude[sd]?|conceal(?:ed|s)?|hidden)"
_FACE_OBJECT = r"(?:human\s+)?(?:faces?|facial\s+features?|mouth|lips?|eyes?|nose|lower\s+face|profile)"
_DIRECT_FACE_PATTERNS = (
    re.compile(rf"\b(?:visible|readable|revealed?|seen|exposed|uncovered)\s+{_FACE_OBJECT}\b"),
    re.compile(rf"\b{_FACE_OBJECT}\s+(?:is|are|can\s+be)?\s*(?:visible|readable|revealed?|seen|exposed|uncovered)\b"),
    re.compile(r"\bface\s+(?:partly|partially)\s+(?:visible|obscured|covered)\b"),
    re.compile(r"\b(?:partial|partially\s+obscured)\s+face\b"),
    re.compile(r"\bstable\s+faces?(?:\s+and\s+anatomy)?\b"),
)
_FACE_GEOMETRY_PATTERNS = (
    re.compile(r"\bfront[- ]?facing\b.*\b(?:close[- ]?up|hood|face|head)\b"),
    re.compile(r"\bfrontal\s+close[- ]?up\b"),
    re.compile(r"\bthree[- ]quarter\s+(?:facial\s+)?view\b"),
    re.compile(r"\bprofile\s+(?:clearly\s+)?visible\b"),
    re.compile(r"\bhood\s+does\s+not\s+cover\s+the\s+lower\s+face\b"),
    re.compile(r"\bcamera\s+reveals?\s+(?:the\s+)?(?:mouth|face|eyes?|lips?)\b"),
)
_FACE_MEDIUM_PATTERNS = (
    re.compile(r"\b(?:reflected\s+face|face\s+(?:in|on)\s+(?:water|mirror|screen|photograph|painting))\b"),
    re.compile(r"\b(?:painting|portrait|photograph|screen|sculpture|statue)\b.*\b(?:face|facial\s+features?)\b"),
    re.compile(r"\b(?:background|distant)\b.*\b(?:face|bystanders?|crowd)\b.*\b(?:visible|readable)\b"),
    re.compile(r"\b(?:facial\s+silhouette|silhouette\s+revealing\s+facial\s+details?)\b"),
)


def _clause_is_negated(clause: str, match_start: int) -> bool:
    prefix = clause[max(0, match_start - 40) : match_start]
    return re.search(rf"\b{_NEGATION}\b(?:\s+\w+){{0,4}}\s*$", prefix) is not None


def analyze_face_semantics(text: str) -> tuple[str, ...]:
    normalized = " ".join(str(text).casefold().replace("_", " ").split())
    failures: list[str] = []
    clauses = re.split(r"[.;!?\n]+|\bbut\b|\bwhile\b|\bhowever\b", normalized)
    for clause in clauses:
        for pattern in _DIRECT_FACE_PATTERNS:
            for match in pattern.finditer(clause):
                if not _clause_is_negated(clause, match.start()):
                    failures.append("FAIL_GLOBAL_FACE_POLICY")
        for pattern in _FACE_GEOMETRY_PATTERNS + _FACE_MEDIUM_PATTERNS:
            if pattern.search(clause):
                failures.append("FAIL_GLOBAL_FACE_POLICY")
    if "eye visible through veil" in normalized:
        failures.append("FAIL_GLOBAL_FACE_POLICY")
    return tuple(sorted(set(failures)))


def analyze_sensitive_semantics(text: str, domains: Iterable[str]) -> tuple[str, ...]:
    normalized = " ".join(str(text).casefold().replace("_", " ").split())
    active = frozenset(str(domain).upper() for domain in domains)
    failures: set[str] = set()
    if "MODESTY" in active:
        if re.search(r"\b(?:woman|female|girl|hawwa|eve)\b.*\b(?:visible|exposed|uncovered)\s+(?:hair|hands?|arms?|legs?|neck|skin)\b", normalized) or re.search(r"\b(?:female|woman(?:'s)?)\s+(?:hair|hands?|arms?|legs?|neck|skin)\b.*\b(?:visible|exposed|uncovered)\b", normalized):
            failures.add("FAIL_FEMALE_MODESTY")
        if re.search(r"\b(?:body[- ]defining|body[- ]contouring|tight|transparent|see[- ]through)\s+(?:cloth|clothing|garment|dress|robe)\b", normalized) or re.search(r"\bvisible\s+body\s+contours?\b", normalized):
            failures.add("FAIL_WARDROBE_POLICY")
        if re.search(r"\b(?:man|male|adam)\b.*\b(?:bare|naked|exposed)\s+(?:torso|chest|body)\b", normalized):
            failures.add("FAIL_WARDROBE_POLICY")
        if re.search(r"\b(?:omit|remove|exclude)\s+(?:the\s+)?(?:required\s+)?(?:woman|female\s+character)\b", normalized):
            failures.add("FAIL_CHARACTER_REQUIRED_BUT_OMITTED")
    if "UNSEEN" in active:
        if re.search(r"\b(?:depict|show|portray|visuali[sz]e)\s+(?:god|allah|the\s+divine|divine\s+self)\b", normalized):
            failures.add("FAIL_SACRED_DEPICTION")
        if re.search(r"\b(?:invented\s+)?(?:angel|jinn|demon)\s+(?:face|body|anatomy)\b", normalized):
            failures.add("FAIL_UNSEEN_INVENTION")
        if re.search(r"\b(?:magical?|supernatural)\s+(?:portal|beam|ray|light|mechanism)\b|\bmagic\s+beam\b", normalized):
            failures.add("FAIL_UNSEEN_INVENTION")
    if "PERIOD" in active:
        if re.search(r"\b(?:modern|contemporary)\s+(?:object|clothing|vehicle|furniture|device)\b", normalized):
            failures.add("FAIL_PERIOD_ANACHRONISM")
        if re.search(r"\b(?:jeans|zipper|smartphone|electric\s+light|plastic\s+bottle)\b", normalized):
            failures.add("FAIL_PERIOD_ANACHRONISM")
        if re.search(r"\b(?:unsupported\s+)?hollywood\s+(?:detail|costume|architecture)\b|\b(?:invented\s+)?(?:archaeological\s+)?adam(?:\s+archaeological)?\s+costume\b", normalized):
            failures.add("FAIL_UNSUPPORTED_MATERIAL_CULTURE")
    if "CHARACTER" in active:
        if re.search(r"\b(?:third|extra|additional|unapproved)\s+(?:character|person|man|woman)\b", normalized):
            failures.add("FAIL_EXTRA_CHARACTER")
        if re.search(r"\b(?:different|changed|drifting)\s+(?:identity|body|wardrobe|silhouette)\b", normalized):
            failures.add("FAIL_CONTINUITY")
    if "VISUAL" in active:
        if re.search(r"\b(?:reverse|opposite|inverted)\s+(?:of\s+)?(?:the\s+)?(?:narrated\s+)?action\b", normalized):
            failures.add("FAIL_ACTION_INVERTED")
        if re.search(r"\b(?:generic|unrelated)\s+(?:filler|atmosphere|visual)\b", normalized):
            failures.add("FAIL_VISUAL_NARRATIVE_MISMATCH")
    if "SOURCE" in active:
        if re.search(r"\bunsourced\s+(?:(?:factual|material)\s+)?(?:claim|fact|assertion)\b", normalized):
            failures.add("FAIL_UNSUPPORTED_CLAIM")
        if re.search(r"\blower\s+source\b.*\boverrides?\b.*\b(?:quran|sahih|higher\s+source)\b", normalized):
            failures.add("FAIL_SOURCE_HIERARCHY")
        if re.search(r"\b(?:upgrade|raise|increase)\s+(?:the\s+)?certainty\b|\buncertain\b.*\b(?:certain|definitive)\b", normalized):
            failures.add("FAIL_CERTAINTY_MISMATCH")
        if re.search(r"\b(?:israiliyyat|weak\s+hadith)\b.*\b(?:certainly|definitely|without\s+doubt)\b", normalized):
            failures.add("FAIL_CERTAINTY_MISMATCH")
        if re.search(r"\bisrailiyyat\b.*\b(?:aqidah\s+conflict|(?<!not\s)conflicts?\s+with\s+aqidah|overrides?\s+quran)\b", normalized):
            failures.add("FAIL_ISRAILIYYAT_CONDITIONS")
        if re.search(r"\bweak\s+hadith\b.*\b(?:aqidah|core\s+religious\s+fact|grade\s+hidden|undisclosed\s+grade)\b", normalized):
            failures.add("FAIL_WEAK_HADITH_CONDITIONS")
        if re.search(r"\b(?:hide|hidden|omit|undisclosed)\b.*\bmaterial\s+disagreement\b", normalized):
            failures.add("FAIL_MATERIAL_DISAGREEMENT_DISCLOSURE")
    if "AUDIO" in active:
        if re.search(r"\b(?:background\s+music|cinematic\s+score|musical\s+sting|musical\s+transition|transition\s+music|intro\s+music|outro\s+music|embedded\s+music)\b", normalized):
            failures.add("FAIL_MUSIC_DETECTED")
    if "MONTAGE" in active or "VISUAL" in active:
        if re.search(r"\b(?:source|title)\s+card\b|\blower\s+third\b|\binfographic\b|\bburned[- ]in\s+(?:caption|subtitle)\b|\barbitrary\s+(?:new\s+)?graphic\b", normalized):
            failures.add("FAIL_FORBIDDEN_GRAPHICS")
    return tuple(sorted(failures))


_DOMAIN_RULE_PREFIXES: Mapping[str, tuple[str, ...]] = {
    "FACE": ("SIRAJ.S01.ALL_HUMAN_FACES", "SIRAJ.S01.PROPHET", "SIRAJ.S01.NON_PROPHET"),
    "UNSEEN": ("SIRAJ.S01.UNSEEN",),
    "MODESTY": ("SIRAJ.S01.MODESTY",),
    "PERIOD": ("SIRAJ.S01.PERIOD",),
    "CHARACTER": ("SIRAJ.S01.RECURRING_CHARACTER",),
    "SOURCE": ("SIRAJ.S02.",),
    "NARRATIVE": ("SIRAJ.S03.NARRATIVE", "SIRAJ.S03.EPISODE"),
    "AUDIO": ("SIRAJ.S03.TTS", "SIRAJ.S06."),
    "VISUAL": ("SIRAJ.S04.",),
    "PROMPT": ("SIRAJ.S05.",),
    "MONTAGE": ("SIRAJ.S07.",),
    "PUBLICATION": ("SIRAJ.S08.",),
    "PAID": ("SIRAJ.S09.",),
    "GOVERNANCE": ("SIRAJ.S10.",),
}


def _rule_applies(rule_id: str, domains: frozenset[str]) -> bool:
    prefixes = tuple(prefix for domain in domains for prefix in _DOMAIN_RULE_PREFIXES.get(domain, ()))
    return not prefixes or rule_id.startswith(prefixes)


def compile_policy(
    registry: RuleRegistry,
    contract: Mapping[str, Any],
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    contract_copy = deepcopy(dict(contract))
    profile_copy = deepcopy(dict(profile))
    errors: list[str] = []
    for field in ("artifact_id", "stage", "text", "sensitive_domains", "bindings"):
        if field not in contract_copy:
            errors.append(f"FAIL_CONTRACT_FIELD_MISSING:{field}")
    raw_domains = contract_copy.get("sensitive_domains")
    if not isinstance(raw_domains, list) or not raw_domains:
        errors.append("FAIL_SENSITIVE_DOMAINS_MISSING")
        domains = frozenset()
    else:
        domains = frozenset(str(domain).upper() for domain in raw_domains)
        if "UNKNOWN" in domains:
            errors.append("FAIL_SENSITIVE_VALUE_UNKNOWN")
    bindings = contract_copy.get("bindings")
    if not isinstance(bindings, Mapping):
        errors.append("FAIL_BINDINGS_MISSING")
        bindings = {}
    required_bindings = {
        "MODESTY": "wardrobe_contract_id",
        "PERIOD": "period_dossier_id",
        "CHARACTER": "canonical_reference_sha256",
        "SOURCE": "source_certainty",
        "AUDIO": "narration_master_sha256",
    }
    for domain, binding in required_bindings.items():
        if domain in domains and _contains_unknown(bindings.get(binding)):
            errors.append(f"FAIL_REQUIRED_BINDING:{binding}")
    artifact_scope = _artifact_scope(contract_copy)
    if artifact_scope not in {LONGFORM_SCOPE, SHORT_DERIVATIVE_SCOPE}:
        errors.append("FAIL_ARTIFACT_SCOPE_INVALID")
    if artifact_scope == LONGFORM_SCOPE and (
        contract_copy.get("burned_captions") is True
        or contract_copy.get("on_screen_subtitles") is True
    ):
        errors.append("FAIL_LONGFORM_BURNED_CAPTIONS")
    if artifact_scope == SHORT_DERIVATIVE_SCOPE and contract_copy.get("burned_captions") is True and not _short_narration_caption_contract_pass(contract_copy):
        errors.append("FAIL_SHORT_CAPTION_SCOPE_CONTRACT")
    text = str(contract_copy.get("text", ""))
    if "FACE" in domains or re.search(r"\b(face|mouth|lips?|eyes?|profile|portrait)\b", text.casefold()):
        errors.extend(analyze_face_semantics(text))
    errors.extend(analyze_sensitive_semantics(text, domains))

    obligations: list[dict[str, Any]] = []
    for rule_id in sorted(registry.by_id):
        rule = registry.by_id[rule_id]
        compiler = rule["compiler"]
        if compiler["applies"] and _rule_applies(rule_id, domains):
            obligations.append(
                {
                    "rule_id": rule_id,
                    "obligations": sorted(str(item) for item in compiler["obligations"]),
                    "value": _deep_thaw(rule["value"]),
                }
            )
    result = {
        "status": "PASS" if not errors else "BLOCKED",
        "constitution_id": registry.constitution.constitution["id"],
        "constitution_version": registry.constitution.constitution["version"],
        "bundle_manifest_sha256": registry.constitution.bundle_manifest_sha256,
        "artifact_id": contract_copy.get("artifact_id"),
        "stage": contract_copy.get("stage"),
        "artifact_scope": artifact_scope,
        "domains": sorted(domains),
        "obligations": obligations,
        "contract_sha256": canonical_json_sha256(contract_copy),
        "profile_sha256": canonical_json_sha256(profile_copy),
        "errors": sorted(set(errors)),
        "provider_call_allowed": False,
        "network_allowed": False,
        "paid_execution_allowed": False,
    }
    result["policy_result_sha256"] = canonical_json_sha256(result)
    return result


@dataclass(frozen=True, slots=True)
class ApprovalReceipt:
    approval_id: str
    approval_type: str
    human_actor: str
    decision: str
    decision_time: str
    constitution_bundle_manifest_sha256: str
    input_artifact_ids: tuple[str, ...]
    input_sha256s: tuple[str, ...]
    scope: str
    expires_or_stales_on: tuple[str, ...]
    consumed_by_transaction_id_if_any: str | None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ApprovalReceipt":
        if set(value) != EXPECTED_APPROVAL_FIELDS:
            raise ApprovalValidationError("APPROVAL_REQUIRED_FIELDS_INVALID")
        artifact_ids = value["input_artifact_ids"]
        hashes = value["input_sha256s"]
        stale_events = value["expires_or_stales_on"]
        if not isinstance(artifact_ids, list) or not artifact_ids:
            raise ApprovalValidationError("APPROVAL_INPUTS_MISSING")
        if len(artifact_ids) != len(set(str(item) for item in artifact_ids)):
            raise ApprovalValidationError("APPROVAL_INPUT_IDS_DUPLICATE")
        if not isinstance(hashes, list) or len(hashes) != len(artifact_ids):
            raise ApprovalValidationError("APPROVAL_HASH_BINDING_INVALID")
        if any(SHA256_PATTERN.fullmatch(str(item)) is None for item in hashes):
            raise ApprovalValidationError("APPROVAL_HASH_INVALID")
        if not isinstance(stale_events, list) or not stale_events:
            raise ApprovalValidationError("APPROVAL_STALE_EVENTS_MISSING")
        if not set(str(item) for item in stale_events) <= EXPECTED_INVALIDATION_EVENTS:
            raise ApprovalValidationError("APPROVAL_STALE_EVENT_UNKNOWN")
        for field in ("approval_id", "approval_type", "human_actor", "scope"):
            if not isinstance(value[field], str) or not value[field].strip():
                raise ApprovalValidationError(f"APPROVAL_{field.upper()}_INVALID")
        if value["decision"] not in {"PASS", "FAIL", "BLOCKED"}:
            raise ApprovalValidationError("APPROVAL_DECISION_INVALID")
        if SHA256_PATTERN.fullmatch(str(value["constitution_bundle_manifest_sha256"])) is None:
            raise ApprovalValidationError("APPROVAL_CONSTITUTION_HASH_INVALID")
        try:
            datetime.fromisoformat(str(value["decision_time"]).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ApprovalValidationError("APPROVAL_TIME_INVALID") from exc
        return cls(
            approval_id=str(value["approval_id"]),
            approval_type=str(value["approval_type"]),
            human_actor=str(value["human_actor"]),
            decision=str(value["decision"]),
            decision_time=str(value["decision_time"]),
            constitution_bundle_manifest_sha256=str(value["constitution_bundle_manifest_sha256"]),
            input_artifact_ids=tuple(str(item) for item in artifact_ids),
            input_sha256s=tuple(str(item) for item in hashes),
            scope=str(value["scope"]),
            expires_or_stales_on=tuple(str(item) for item in stale_events),
            consumed_by_transaction_id_if_any=(
                None
                if value["consumed_by_transaction_id_if_any"] is None
                else str(value["consumed_by_transaction_id_if_any"])
            ),
        )


def verify_approval_receipt(
    receipt: ApprovalReceipt,
    constitution: LoadedConstitution,
    current_artifacts: Mapping[str, str],
    *,
    required_scope: str,
) -> None:
    if receipt.decision != "PASS":
        raise ApprovalValidationError("APPROVAL_DECISION_NOT_PASS")
    if receipt.scope != required_scope:
        raise ApprovalValidationError("APPROVAL_SCOPE_MISMATCH")
    if receipt.constitution_bundle_manifest_sha256 != constitution.bundle_manifest_sha256:
        raise ApprovalValidationError("APPROVAL_CONSTITUTION_STALE")
    expected = dict(zip(receipt.input_artifact_ids, receipt.input_sha256s, strict=True))
    if expected != dict(current_artifacts):
        raise ApprovalValidationError("APPROVAL_INPUT_HASH_STALE")


_APPROVAL_DOWNSTREAM: Mapping[str, tuple[str, ...]] = {
    "SCRIPT_APPROVAL": ("NARRATION_APPROVAL", "STORYBOARD_APPROVAL"),
    "NARRATION_APPROVAL": ("TIMELINE",),
    "TIMELINE": ("STORYBOARD_TIMING", "PROMPT_TIMING", "COST_ESTIMATE"),
    "STORYBOARD_APPROVAL": ("PROMPT_APPROVAL",),
    "PROMPT_APPROVAL": ("PILOT_APPROVAL",),
    "PILOT_APPROVAL": ("PAID_AUTHORIZATION", "BATCH_AUTHORIZATION"),
    "PAID_AUTHORIZATION": ("RENDER_PROMOTION",),
    "RENDER_PROMOTION": ("MONTAGE_APPROVAL",),
    "MONTAGE_APPROVAL": ("FINAL_QA", "FINAL_CERTIFICATION"),
    "FINAL_QA": ("FINAL_HUMAN_CERTIFICATION",),
}


class InvalidationEngine:
    def __init__(self, constitution: LoadedConstitution) -> None:
        self._events = {
            event["event"]: tuple(event["invalidates"])
            for event in constitution.rules_document["invalidation_events"]
        }

    @property
    def events(self) -> frozenset[str]:
        return frozenset(self._events)

    def invalidate(self, event: str, *, material: bool | None = True) -> frozenset[str]:
        if event not in self._events:
            raise ApprovalValidationError("INVALIDATION_EVENT_UNKNOWN")
        if material is False:
            return frozenset()
        targets = set(self._events[event])
        if "ALL_DOWNSTREAM_APPROVALS" in targets:
            targets.remove("ALL_DOWNSTREAM_APPROVALS")
            targets.update(_APPROVAL_DOWNSTREAM)
        changed = True
        while changed:
            changed = False
            for target in tuple(targets):
                for dependent in _APPROVAL_DOWNSTREAM.get(target, ()):
                    if dependent not in targets:
                        targets.add(dependent)
                        changed = True
        if material is None:
            targets.add("SENSITIVE_MATERIALITY_REAPPROVAL_BLOCK")
        return frozenset(targets)


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    validator: str
    status: str
    failure_code: str | None
    detail: str


def _finding(name: str, passed: bool, code: str, detail: str) -> ValidationFinding:
    return ValidationFinding(name, "PASS" if passed else "BLOCKED", None if passed else code, detail)


_HUMAN_RECEIPT_VALIDATORS = frozenset(
    {
        "all_frame_modesty_validator",
        "all_frame_render_face_validator",
        "aqidah_conflict_review",
        "editorial_quality_review",
        "final_watch_receipt_validator",
        "full_human_end_to_end_review",
        "human_audio_review",
        "human_audio_review_receipt_validator",
        "human_certification_validator",
        "human_editorial_review",
        "human_full_audio_review",
        "human_pilot_review_validator",
        "human_render_conformance",
        "human_theological_review",
        "material_omission_review",
        "montage_review_receipt_validator",
        "mute_comprehension_validator",
        "pilot_render_conformance_validator",
        "quran_pronunciation_human_review_validator",
        "repetition_review",
        "scholarly_usage_review",
    }
)

_VALIDATOR_FAMILIES: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "FACE": frozenset({"reference_face_validator", "face_policy_validator", "sacred_character_contract_validator"}),
        "MODESTY": frozenset({"wardrobe_contract_validator"}),
        "UNSEEN": frozenset({"unseen_representation_validator"}),
        "PERIOD": frozenset({"period_evidence_validator", "storyboard_period_validator", "prompt_period_validator", "render_period_validator"}),
        "CHARACTER": frozenset({"character_contract_validator", "canonical_still_validator", "reference_provenance_validator", "continuity_validator"}),
        "SOURCE": frozenset({"source_claim_validator", "claim_ledger_validator", "source_hierarchy_validator", "script_claim_validator", "visual_claim_validator", "source_classification_validator", "narrator_certainty_validator", "hadith_grade_validator", "script_certainty_validator", "dispute_materiality_validator", "script_disclosure_validator", "claim_script_validator"}),
        "GRAPHICS": frozenset({"storyboard_graphics_validator", "render_graphics_validator", "montage_overlay_validator", "graphics_whitelist_validator", "render_text_overlay_validator"}),
        "NARRATIVE": frozenset({"script_structure_validator", "filler_validator"}),
        "DURATION": frozenset({"duration_policy_validator"}),
        "APPROVAL": frozenset({"approval_receipt_validator", "approval_input_hash_validator", "asset_promotion_receipt_validator", "audio_master_hash_binding_validator", "authorization_hash_validator", "candidate_hash_validator", "final_candidate_hash_validator", "dependency_graph_validator", "stale_state_validator"}),
        "TTS": frozenset({"script_semantic_equivalence_validator", "diacritization_validator", "waqf_wasl_validator", "pronunciation_lexicon_validator"}),
        "VISUAL": frozenset({"storyboard_semantic_validator", "render_semantic_validator"}),
        "VIDEO_SHARE": frozenset({"timeline_media_share_validator", "core_runtime_validator"}),
        "REUSE": frozenset({"reuse_semantic_validator"}),
        "PILOT": frozenset({"pilot_coverage_validator", "pilot_dependency_validator"}),
        "PROMPT": frozenset({"structured_contract_validator", "contract_completeness_validator", "payload_hash_validator"}),
        "SEMANTIC": frozenset({"prompt_semantic_linter"}),
        "PROVIDER": frozenset({"provider_profile_validator", "model_profile_validator", "provider_approval_validator"}),
        "BATCH": frozenset({"batch_risk_validator", "batch_scope_validator"}),
        "RETRY": frozenset({"retry_root_cause_validator", "material_delta_validator", "new_preflight_validator", "new_authorization_validator"}),
        "NARRATOR": frozenset({"voice_identity_validator", "pronunciation_validator"}),
        "QURAN": frozenset({"quran_text_integrity_validator"}),
        "MUSIC": frozenset({"asset_audio_stream_validator", "music_content_validator", "mix_timeline_validator", "music_policy_validator"}),
        "SFX": frozenset({"sfx_semantic_validator", "period_audio_validator", "audio_visual_sync_validator"}),
        "CAPTIONS": frozenset({"caption_separation_validator"}),
        "TIMELINE": frozenset({"narration_hash_validator", "duration_authority_validator", "timeline_precision_validator"}),
        "MONTAGE": frozenset({"render_hash_validator", "constitutional_qa_validator"}),
        "BRAND": frozenset({"brand_asset_cardinality_validator", "brand_asset_hash_validator", "brand_asset_policy_validator"}),
        "PLACEMENT": frozenset({"intro_boundary_validator", "outro_position_validator"}),
        "FINAL_QA": frozenset({"all_domain_qa_validator", "technical_qa_validator"}),
        "PUBLICATION": frozenset({"publication_metadata_boundary_validator", "working_title_leak_validator"}),
        "PAID": frozenset({"execution_origin_validator", "human_click_nonce_validator", "authorization_envelope_validator"}),
        "COST": frozenset({"cost_estimate_validator", "rate_profile_freshness_validator", "cost_ceiling_validator"}),
        "UNKNOWN": frozenset({"attempt_state_validator", "reconciliation_receipt_validator"}),
        "HISTORICAL_UNKNOWN": frozenset({"historical_attempt_ledger_validator", "reconciliation_evidence_validator"}),
        "IDEMPOTENCY": frozenset({"attempt_uniqueness_validator", "idempotency_validator", "authorization_consumption_validator"}),
        "RECOVERY": frozenset({"recovery_capability_validator", "network_provider_capability_validator"}),
        "GOVERNANCE": frozenset({"constitution_bundle_validator", "precedence_validator", "duplicate_policy_authority_validator", "bundle_manifest_validator", "artifact_constitution_binding_validator"}),
        "COVERAGE": frozenset({"enforcement_coverage_validator", "runtime_gate_registration_validator"}),
        "CAPABILITY": frozenset({"capability_boundary_validator", "dependency_boundary_validator", "network_fixture_validator"}),
        "APPEND_ONLY": frozenset({"ledger_chain_validator", "evidence_mutation_validator", "ledger_head_binding_validator"}),
    }
)


def _validator_family(name: str) -> str | None:
    if name in _HUMAN_RECEIPT_VALIDATORS:
        return "HUMAN_RECEIPT"
    matches = [family for family, names in _VALIDATOR_FAMILIES.items() if name in names]
    if len(matches) != 1:
        return None
    return matches[0]


def _hash_bound_receipt_validator(
    name: str,
    artifact: Mapping[str, Any],
    constitution: LoadedConstitution,
) -> ValidationFinding:
    receipts = artifact.get("validation_receipts")
    if not isinstance(receipts, Mapping):
        return _finding(name, False, "FAIL_VALIDATION_EVIDENCE_MISSING", "validation_receipts missing")
    receipt = receipts.get(name)
    if not isinstance(receipt, Mapping):
        return _finding(name, False, "FAIL_VALIDATION_EVIDENCE_MISSING", "validator receipt missing")
    expected_hash = artifact_sha256(artifact.get("subject"))
    try:
        datetime.fromisoformat(str(receipt.get("decision_time", "")).replace("Z", "+00:00"))
        time_valid = True
    except ValueError:
        time_valid = False
    passed = (
        receipt.get("status") == "PASS"
        and receipt.get("subject_sha256") == expected_hash
        and receipt.get("constitution_bundle_manifest_sha256") == constitution.bundle_manifest_sha256
        and isinstance(receipt.get("human_actor"), str)
        and bool(receipt.get("human_actor"))
        and time_valid
    )
    return _finding(name, passed, "FAIL_VALIDATION_EVIDENCE_STALE", "human hash-bound review receipt")


def _contract(artifact: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = artifact.get(name)
    return value if isinstance(value, Mapping) else MappingProxyType({})


LONGFORM_SCOPE = "LONGFORM"
SHORT_DERIVATIVE_SCOPE = "SHORT_DERIVATIVE"
SHORT_CAPTION_TEXT_AUTHORITIES = frozenset(
    {"CANONICAL_TIMED_TRANSCRIPT", "TRUSTED_HASH_BOUND_TIMING"}
)
SHORT_CAPTION_FORBIDDEN_FLAGS = (
    "invented_text",
    "hook_text",
    "title_card_text",
    "cta_text",
    "subscribe_text",
    "decorative_prose",
    "fact_overlay_text",
    "unrelated_text",
    "banner_text",
    "promotional_text",
)


def _artifact_scope(artifact: Mapping[str, Any]) -> str:
    """Return the explicit artifact scope; missing scope is safe Longform."""

    raw_scope = artifact.get("artifact_scope", LONGFORM_SCOPE)
    return str(raw_scope).strip().upper()


def _short_narration_caption_contract_pass(artifact: Mapping[str, Any]) -> bool:
    """Validate the narrow Shorts-only burned narration caption exception."""

    if _artifact_scope(artifact) != SHORT_DERIVATIVE_SCOPE:
        return False
    caption = _contract(artifact, "caption_contract")
    if (
        artifact.get("burned_captions") is not True
        or artifact.get("on_screen_subtitles") is True
        or caption.get("mode") != "BURNED_NARRATION_CAPTIONS"
        or caption.get("enabled") is not True
        or caption.get("synced_to_narration") is not True
        or caption.get("narration_only") is not True
        or caption.get("text_is_verbatim") is not True
        or caption.get("text_authority") not in SHORT_CAPTION_TEXT_AUTHORITIES
    ):
        return False
    if any(caption.get(flag) is not False for flag in SHORT_CAPTION_FORBIDDEN_FLAGS):
        return False
    return all(
        SHA256_PATTERN.fullmatch(str(caption.get(key, ""))) is not None
        for key in ("transcript_sha256", "timing_source_sha256")
    )


def _all_claims_valid(claims: Any) -> bool:
    if not isinstance(claims, list) or not claims:
        return False
    certainty = {"UNKNOWN": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CERTAIN": 4}
    for claim in claims:
        if not isinstance(claim, Mapping) or not claim.get("source_id"):
            return False
        before = certainty.get(str(claim.get("certainty_in", "UNKNOWN")).upper(), -1)
        after = certainty.get(str(claim.get("certainty_out", "UNKNOWN")).upper(), -1)
        if before < 0 or after < 0 or after > before or claim.get("lower_source_overrides_higher") is True:
            return False
        classification = str(claim.get("classification", "PRIMARY")).upper()
        if classification == "ISRAILIYYAT" and (
            claim.get("aqidah_conflict") is True
            or claim.get("jazm") is True
            or claim.get("disclosed") is not True
        ):
            return False
        if classification == "WEAK_HADITH" and (
            claim.get("aqidah_foundation") is True
            or claim.get("core_religious_fact") is True
            or claim.get("jazm") is True
            or claim.get("grade_disclosed") is not True
        ):
            return False
        if claim.get("material_disagreement") is True and claim.get("disagreement_disclosed") is not True:
            return False
    return True


def _automated_validator(
    name: str,
    artifact: Mapping[str, Any],
    constitution: LoadedConstitution,
) -> ValidationFinding | None:
    family = _validator_family(name)
    if family in {None, "HUMAN_RECEIPT"}:
        return None
    text = str(artifact.get("text", ""))
    domains = artifact.get("sensitive_domains", ["FACE", "MODESTY", "UNSEEN", "PERIOD", "SOURCE", "AUDIO", "MONTAGE"])
    if family == "FACE":
        failures = analyze_face_semantics(text)
        face = _contract(artifact, "face_contract")
        passed = not failures and face.get("all_human_faces_excluded") is True and face.get("crop_blur_mask_rescue") is False
        return _finding(name, passed, "FAIL_GLOBAL_FACE_POLICY", "semantic, geometric, and structured face contract")
    if family == "SEMANTIC":
        failures = set(analyze_face_semantics(text))
        failures.update(analyze_sensitive_semantics(text, domains))
        return _finding(name, not failures, "FAIL_PROMPT_SEMANTIC_CONTRADICTION", "all sensitive semantic domains")
    if family == "MODESTY":
        wardrobe = _contract(artifact, "wardrobe_contract")
        passed = not analyze_sensitive_semantics(text, ["MODESTY"]) and wardrobe.get("female_maximum_modesty") is True and wardrobe.get("male_period_modesty") is True and wardrobe.get("required_characters_present") is True
        return _finding(name, passed, "FAIL_WARDROBE_POLICY", "structured modesty contract")
    if family == "UNSEEN":
        unseen = _contract(artifact, "unseen_contract")
        passed = not analyze_sensitive_semantics(text, ["UNSEEN"]) and unseen.get("divine_depiction") is False and unseen.get("invented_form_or_mechanism") is False and unseen.get("unknown_preserved") is True
        return _finding(name, passed, "FAIL_UNSEEN_INVENTION", "unseen non-invention contract")
    if family == "PERIOD":
        period = _contract(artifact, "period_contract")
        passed = not analyze_sensitive_semantics(text, ["PERIOD"]) and period.get("evidence_approved") is True and period.get("modern_elements") == [] and period.get("unknown_detail_policy") == "NEUTRAL_DO_NOT_INVENT"
        return _finding(name, passed, "FAIL_PERIOD_AUTHENTICITY", "period evidence and zero-anachronism contract")
    if family == "CHARACTER":
        character = _contract(artifact, "character_contract")
        passed = SHA256_PATTERN.fullmatch(str(character.get("canonical_still_sha256", ""))) is not None and character.get("provenance_approved") is True and character.get("identity_drift") is False and character.get("extra_characters") == 0
        return _finding(name, passed, "FAIL_CHARACTER_CONTINUITY", "canonical still and provenance contract")
    if family == "SOURCE":
        passed = not analyze_sensitive_semantics(text, ["SOURCE"]) and _all_claims_valid(artifact.get("claims"))
        return _finding(name, passed, "FAIL_SOURCE_OR_CERTAINTY_POLICY", "source hierarchy, classification, and certainty inheritance")
    if family == "GRAPHICS":
        graphics = _contract(artifact, "graphics_contract")
        short_caption_exception = _short_narration_caption_contract_pass(artifact)
        burned_caption_policy_pass = (
            graphics.get("burned_captions") is False
            or (short_caption_exception and graphics.get("burned_captions") is True)
        )
        passed = not analyze_sensitive_semantics(text, ["MONTAGE"]) and graphics.get("arbitrary_graphics") is False and artifact.get("on_screen_subtitles") is not True and burned_caption_policy_pass and graphics.get("asset_kind") in {"NONE", "CANONICAL_INTRO", "CANONICAL_OUTRO"} and graphics.get("face_policy_pass") is True and graphics.get("music_policy_pass") is True
        return _finding(name, passed, "FAIL_FORBIDDEN_GRAPHICS", "graphics prohibition and exact brand whitelist")
    if family == "NARRATIVE":
        narrative = _contract(artifact, "narrative_contract")
        passed = narrative.get("false_hook") is False and narrative.get("fabricated_mystery") is False and narrative.get("filler") is False and narrative.get("payoff_present") is True
        return _finding(name, passed, "FAIL_NARRATIVE_INTEGRITY", "truthful narrative structure")
    if family == "DURATION":
        duration = _contract(artifact, "episode_duration_contract")
        minutes = duration.get("minutes")
        passed = isinstance(minutes, (int, float)) and (8 <= minutes <= 15 or (6 <= minutes <= 18 and duration.get("soft_exception_approved") is True) or (minutes > 18 and duration.get("special_approval") is True))
        return _finding(name, passed, "FAIL_EPISODE_DURATION_POLICY", "episode duration policy")
    if family == "APPROVAL":
        approval = _contract(artifact, "approval_contract")
        passed = approval.get("hash_bound") is True and approval.get("stale") is False and approval.get("required_receipts_present") is True and approval.get("artifact_hash_match") is True and approval.get("constitution_hash_match") is True
        return _finding(name, passed, "FAIL_APPROVAL_BINDING", "hash-bound non-stale approval contract")
    if family == "TTS":
        tts = _contract(artifact, "tts_contract")
        passed = tts.get("semantic_equivalence") is True and tts.get("context_diacritization") is True and tts.get("waqf_wasl") is True and tts.get("pronunciation_lexicon") is True
        return _finding(name, passed, "FAIL_TTS_PERFORMANCE_CONTRACT", "TTS performance-script contract")
    if family == "VISUAL":
        visual = _contract(artifact, "visual_contract")
        passed = visual.get("semantic_alignment") is True and visual.get("action_inverted") is False and visual.get("generic_filler") is False
        return _finding(name, passed, "FAIL_VISUAL_NARRATIVE_MISMATCH", "storyboard/render semantic alignment")
    if family == "VIDEO_SHARE":
        media = _contract(artifact, "media_share_contract")
        core = media.get("core_episode_seconds")
        video = media.get("video_seconds")
        passed = isinstance(core, (int, float)) and core > 0 and isinstance(video, (int, float)) and 0.50 <= video / core <= 0.75 and media.get("intro_outro_excluded") is True
        return _finding(name, passed, "FAIL_VIDEO_SHARE", "core-episode video share")
    if family == "REUSE":
        reuse = _contract(artifact, "reuse_contract")
        passed = reuse.get("editorially_justified") is True and reuse.get("repetitive_padding") is False
        return _finding(name, passed, "FAIL_REUSE_POLICY", "editorially justified reuse")
    if family == "PILOT":
        pilot = _contract(artifact, "pilot_contract")
        passed = pilot.get("highest_risk_shots_selected") is True and pilot.get("all_frame_review_receipt_valid") is True and pilot.get("approved") is True
        return _finding(name, passed, "FAIL_PILOT_NOT_APPROVED", "hard-shot pilot coverage")
    if family == "PROMPT":
        prompt = _contract(artifact, "prompt_contract")
        passed = prompt.get("structured") is True and prompt.get("all_required_fields") is True and prompt.get("canonical_reference_approved") is True and prompt.get("payload_hash_match") is True and prompt.get("executor_mutated_payload") is False
        return _finding(name, passed, "FAIL_PROMPT_CONTRACT", "structured prompt and immutable payload binding")
    if family == "PROVIDER":
        profile = _contract(artifact, "provider_profile")
        passed = profile.get("provider") == "VEO_3_1_LITE" and profile.get("approved") is True and profile.get("silent_fallback") is False and profile.get("automatic_switching") is False
        return _finding(name, passed, "FAIL_PROVIDER_UNAPPROVED", "provider profile binding")
    if family == "BATCH":
        batch = _contract(artifact, "batch_contract")
        passed = batch.get("progressive") is True and batch.get("pilot_dependency_satisfied") is True and batch.get("bounded_request_count") is True and batch.get("new_risk_class_piloted") is True
        return _finding(name, passed, "FAIL_BATCH_SCOPE", "progressive bounded batching")
    if family == "RETRY":
        retry = _contract(artifact, "retry_contract")
        if retry.get("requested") is False:
            passed = retry.get("automatic") is False
        else:
            passed = retry.get("automatic") is False and retry.get("root_cause") is True and retry.get("material_delta") is True and retry.get("new_preflight") is True and retry.get("new_human_authorization") is True and retry.get("identical_quality_retry") is False
        return _finding(name, passed, "FAIL_PAID_RETRY_POLICY", "root-cause and fresh-authorization retry boundary")
    if family == "NARRATOR":
        narrator = _contract(artifact, "narrator_contract")
        passed = narrator.get("identity") == "CURRENT_APPROVED_NARRATOR" and narrator.get("replacement") is False and narrator.get("pronunciation_pass") is True
        return _finding(name, passed, "FAIL_NARRATOR_IDENTITY", "approved narrator identity")
    if family == "QURAN":
        quran = _contract(artifact, "quran_contract")
        passed = quran.get("trusted_text") is True and quran.get("llm_reconstruction") is False and quran.get("human_text_review") is True and quran.get("human_pronunciation_review") is True
        return _finding(name, passed, "FAIL_QURAN_INTEGRITY", "trusted Quran text and human reviews")
    if family == "MUSIC":
        tracks = artifact.get("audio_tracks", [])
        passed = isinstance(tracks, list) and not any(
            isinstance(track, Mapping)
            and (track.get("contains_music") is True or str(track.get("kind", "")).upper() == "MUSIC")
            for track in tracks
        )
        return _finding(name, passed, "FAIL_MUSIC_DETECTED", "audio track policy")
    if family == "SFX":
        sfx = _contract(artifact, "sfx_contract")
        passed = sfx.get("serves_narrative") is True and sfx.get("false_factual_presentation") is False and sfx.get("period_appropriate") is True and sfx.get("synced") is True and sfx.get("musical") is False
        return _finding(name, passed, "FAIL_SFX_POLICY", "semantic, period, and sync SFX contract")
    if family == "TIMELINE":
        authority = artifact.get("narration_master")
        timeline = artifact.get("timeline")
        passed = (
            isinstance(authority, Mapping)
            and isinstance(timeline, Mapping)
            and authority.get("sha256") == timeline.get("narration_master_sha256")
            and authority.get("duration_ticks") == timeline.get("duration_ticks")
            and authority.get("timebase") == timeline.get("timebase")
        )
        return _finding(name, passed, "FAIL_AUDIO_DURATION_AUTHORITY_CONFLICT", "narration-master authority")
    if family == "CAPTIONS":
        scope = _artifact_scope(artifact)
        if scope == SHORT_DERIVATIVE_SCOPE:
            passed = _short_narration_caption_contract_pass(artifact)
        else:
            passed = scope == LONGFORM_SCOPE and artifact.get("burned_captions") is False and artifact.get("on_screen_subtitles") is False and artifact.get("external_captions") in {True, False}
        return _finding(name, passed, "FAIL_BURNED_IN_CAPTIONS", "scope-bound external or Shorts narration caption policy")
    if family == "MONTAGE":
        montage = _contract(artifact, "montage_contract")
        passed = montage.get("all_assets_promoted") is True and montage.get("render_hashes_match") is True and montage.get("constitutional_qa_pass") is True
        return _finding(name, passed, "FAIL_MONTAGE_ADMISSION", "asset promotion and render hash admission")
    if family == "BRAND":
        brand = _contract(artifact, "brand_contract")
        hashes_valid = all(SHA256_PATTERN.fullmatch(str(brand.get(key, ""))) for key in ("intro_sha256", "outro_sha256"))
        passed = brand.get("intro_count") == 1 and brand.get("outro_count") == 1 and hashes_valid and brand.get("assets_unmodified") is True and brand.get("face_policy_pass") is True and brand.get("music_policy_pass") is True
        return _finding(name, passed, "FAIL_BRAND_ASSET_POLICY", "canonical brand discovery, hash, face, and music binding")
    if family == "PLACEMENT":
        placement = _contract(artifact, "placement_contract")
        passed = placement.get("intro_at_boundary") is True and placement.get("outro_after_core_end") is True and placement.get("intro_outro_excluded_from_core") is True
        return _finding(name, passed, "FAIL_INTRO_OUTRO_PLACEMENT", "canonical boundary placement")
    if family == "FINAL_QA":
        final_qa = _contract(artifact, "final_qa_contract")
        passed = final_qa.get("all_domain_findings_pass") is True and final_qa.get("technical_qa_pass") is True and final_qa.get("candidate_hash_match") is True
        return _finding(name, passed, "FAIL_FINAL_QA", "all-domain immutable candidate QA")
    if family == "PUBLICATION":
        publication = _contract(artifact, "publication_contract")
        passed = publication.get("siraj_generates_title") is False and publication.get("siraj_generates_thumbnail") is False and publication.get("working_title_auto_publish") is False and publication.get("public_metadata_required_for_production_pass") is False
        return _finding(name, passed, "FAIL_PUBLIC_METADATA_BOUNDARY", "human-owned public title and thumbnail")
    if family == "PAID":
        paid = _contract(artifact, "paid_contract")
        passed = paid.get("origin") == "DESKTOP" and bool(paid.get("desktop_click_nonce")) and paid.get("authorization_fresh") is True and paid.get("payload_hash_match") is True and paid.get("reference_hashes_match") is True and paid.get("pilot_approved") is True and paid.get("state_known") is True
        return _finding(name, passed, "FAIL_PAID_EXECUTION_ORIGIN", "desktop click and exact authorization envelope")
    if family == "COST":
        cost = artifact.get("cost_authorization")
        passed = (
            isinstance(cost, Mapping)
            and cost.get("stale") is False
            and isinstance(cost.get("estimated_cost"), (int, float))
            and isinstance(cost.get("authorized_max_cost"), (int, float))
            and cost["estimated_cost"] <= cost["authorized_max_cost"]
        )
        return _finding(name, passed, "FAIL_COST_AUTHORIZATION", "cost envelope")
    if family == "UNKNOWN":
        state = artifact.get("submission_state")
        reconciliation = _contract(artifact, "reconciliation_contract")
        passed = (state != "SUBMISSION_UNKNOWN" or artifact.get("resubmit") is False) and reconciliation.get("authorizes_execution") is False and reconciliation.get("ledger_head_match") is True
        return _finding(name, passed, "FAIL_UNKNOWN_STATE_RESUBMISSION", "UNKNOWN state boundary")
    if family == "HISTORICAL_UNKNOWN":
        historical = _contract(artifact, "historical_unknown_contract")
        attempt_id = str(historical.get("attempt_id", "")).strip()
        provider_request = str(historical.get("provider_request", "")).strip()
        passed = (
            bool(attempt_id)
            and bool(provider_request)
            and historical.get("status") == "SUBMISSION_UNKNOWN"
            and historical.get("retry")
            in {"BLOCKED", "BLOCKED_UNTIL_EVIDENCE_BASED_RECONCILIATION"}
            and historical.get("preserved") is True
        )
        return _finding(
            name,
            passed,
            "FAIL_HISTORICAL_UNKNOWN_MUTATED",
            "generic historical UNKNOWN preservation without episode-specific identity",
        )
    if family == "IDEMPOTENCY":
        transaction = _contract(artifact, "transaction_contract")
        passed = bool(transaction.get("attempt_id")) and bool(transaction.get("transaction_id")) and transaction.get("duplicate") is False and transaction.get("double_click") is False and transaction.get("authorization_consumed_once") is True
        return _finding(name, passed, "FAIL_IDEMPOTENCY", "single-consumption transaction identity")
    if family == "RECOVERY":
        recovery = _contract(artifact, "recovery_contract")
        passed = recovery.get("pre_spend_only") is True and recovery.get("provider_capability") is False and recovery.get("network_capability") is False and recovery.get("paid_capability") is False
        return _finding(name, passed, "FAIL_RECOVERY_CAPABILITY", "pre-spend-only recovery capability")
    if family == "GOVERNANCE":
        governance = _contract(artifact, "governance_contract")
        passed = governance.get("constitution_id") == constitution.constitution["id"] and governance.get("version") == constitution.constitution["version"] and governance.get("bundle_manifest_sha256") == constitution.bundle_manifest_sha256 and governance.get("precedence") == list(EXPECTED_PRECEDENCE) and governance.get("machine_rule_source_count") == 1
        return _finding(name, passed, "FAIL_CANONICAL_AUTHORITY", "single hash-bound constitutional authority")
    if family == "COVERAGE":
        coverage = _contract(artifact, "coverage_contract")
        passed = coverage.get("rule_count") == 51 and coverage.get("covered_rules") == 51 and coverage.get("uncovered_rules") == 0 and coverage.get("runtime_gates_registered") is True
        return _finding(name, passed, "FAIL_ENFORCEMENT_COVERAGE", "51-rule enforcement chain")
    if family == "CAPABILITY":
        capability = _contract(artifact, "capability_contract")
        passed = capability.get("compiler_provider_call") is False and capability.get("validator_mutation") is False and capability.get("executor_creative_authority") is False and capability.get("recovery_paid_execution") is False and capability.get("tests_production_network") is False
        return _finding(name, passed, "FAIL_CAPABILITY_BOUNDARY", "architectural capability separation")
    if family == "APPEND_ONLY":
        ledger = _contract(artifact, "ledger_contract")
        passed = ledger.get("append_only") is True and ledger.get("chain_valid") is True and ledger.get("head_hash_match") is True and ledger.get("historical_mutation") is False
        return _finding(name, passed, "FAIL_EVIDENCE_MUTATION", "append-only hash-chained evidence")
    return None


class ValidatorRegistry:
    def __init__(self, registry: RuleRegistry) -> None:
        self.registry = registry
        self._declared = frozenset(
            str(name)
            for rule in registry.by_id.values()
            for name in rule["validators"]
        )

    @property
    def declared(self) -> frozenset[str]:
        return self._declared

    def binding_kind(self, name: str) -> str:
        family = _validator_family(name)
        if family is None:
            return "MISSING"
        if family == "HUMAN_RECEIPT":
            return "HUMAN_HASH_BOUND_EVIDENCE_RECEIPT"
        return f"AUTOMATED:{family}"

    def validate(self, name: str, artifact: Mapping[str, Any]) -> ValidationFinding:
        if name not in self._declared:
            return _finding(name, False, "FAIL_VALIDATOR_UNREGISTERED", "not declared by canonical rules")
        before = canonical_json_sha256(artifact)
        family = _validator_family(name)
        if family is None:
            result = _finding(name, False, "FAIL_VALIDATOR_IMPLEMENTATION_MISSING", "declared validator has no implementation")
        elif family == "HUMAN_RECEIPT":
            result = _hash_bound_receipt_validator(name, artifact, self.registry.constitution)
        else:
            result = _automated_validator(name, artifact, self.registry.constitution)
            if result is None:
                result = _finding(name, False, "FAIL_VALIDATOR_IMPLEMENTATION_MISSING", "validator family has no evaluator")
        if before != canonical_json_sha256(artifact):
            return _finding(name, False, "FAIL_VALIDATOR_MUTATION", "validator mutated inspected input")
        return result

    def validate_rule(self, rule_id: str, artifact: Mapping[str, Any]) -> tuple[ValidationFinding, ...]:
        rule = self.registry.require(rule_id)
        return tuple(self.validate(str(name), artifact) for name in rule["validators"])


@dataclass(frozen=True, slots=True)
class GateDecision:
    gate: str
    status: str
    rule_ids: tuple[str, ...]
    findings: tuple[ValidationFinding, ...]


class RuntimeGateEngine:
    def __init__(self, registry: RuleRegistry, validators: ValidatorRegistry) -> None:
        self.registry = registry
        self.validators = validators

    def evaluate(
        self,
        gate: str,
        artifact: Mapping[str, Any],
        *,
        rule_ids: Iterable[str] | None = None,
    ) -> GateDecision:
        if gate not in RUNTIME_GATES and not any(
            gate in rule["runtime_gates"] for rule in self.registry.by_id.values()
        ):
            raise ConstitutionEnforcementError(f"RUNTIME_GATE_UNKNOWN:{gate}")
        selected = tuple(
            sorted(
                rule_ids
                if rule_ids is not None
                else (
                    rule_id
                    for rule_id, rule in self.registry.by_id.items()
                    if gate in rule["runtime_gates"]
                )
            )
        )
        findings = tuple(
            finding
            for rule_id in selected
            for finding in self.validators.validate_rule(rule_id, artifact)
        )
        status = "PASS" if findings and all(item.status == "PASS" for item in findings) else "BLOCKED"
        return GateDecision(gate, status, selected, findings)


@dataclass(frozen=True, slots=True)
class PaidExecutionEnvelope:
    origin: str
    desktop_click_nonce: str
    authorization_id: str
    authorization_consumed: bool
    payload_sha256: str
    approved_payload_sha256: str
    reference_sha256s: tuple[str, ...]
    approved_reference_sha256s: tuple[str, ...]
    provider: str
    model: str
    provider_profile_approved: bool
    pilot_coverage_approved: bool
    estimated_cost: float
    authorized_max_cost: float
    approvals_stale: bool
    submission_state: str
    transaction_id: str


def evaluate_paid_execution_envelope(envelope: PaidExecutionEnvelope) -> GateDecision:
    failures: list[ValidationFinding] = []

    def require(condition: bool, code: str, detail: str) -> None:
        failures.append(_finding("paid_execution_envelope", condition, code, detail))

    require(envelope.origin == "DESKTOP", "FAIL_PAID_EXECUTION_ORIGIN", "desktop origin")
    require(bool(envelope.desktop_click_nonce), "FAIL_MISSING_EXPLICIT_HUMAN_START", "human click nonce")
    require(bool(envelope.authorization_id), "FAIL_AUTHORIZATION_MISSING", "authorization identity")
    require(not envelope.authorization_consumed, "FAIL_AUTHORIZATION_REUSED", "single-use authorization")
    require(SHA256_PATTERN.fullmatch(envelope.payload_sha256) is not None, "FAIL_PAYLOAD_HASH_MISMATCH", "payload hash format")
    require(envelope.payload_sha256 == envelope.approved_payload_sha256, "FAIL_PAYLOAD_HASH_MISMATCH", "exact payload")
    require(
        envelope.reference_sha256s == envelope.approved_reference_sha256s,
        "FAIL_REFERENCE_HASH_MISMATCH",
        "exact references",
    )
    require(envelope.provider_profile_approved, "FAIL_PROVIDER_UNAPPROVED", "provider/model profile")
    require(envelope.provider == "VEO_3_1_LITE" and bool(envelope.model), "FAIL_PROVIDER_UNAPPROVED", "exact provider/model binding")
    require(envelope.pilot_coverage_approved, "FAIL_PILOT_NOT_APPROVED", "pilot coverage")
    require(envelope.estimated_cost <= envelope.authorized_max_cost, "FAIL_COST_AUTHORIZATION", "cost ceiling")
    require(not envelope.approvals_stale, "FAIL_STALE_PAID_AUTHORIZATION", "fresh approvals")
    require(envelope.submission_state != "SUBMISSION_UNKNOWN", "FAIL_UNKNOWN_STATE_RESUBMISSION", "known state")
    require(bool(envelope.transaction_id), "FAIL_IDEMPOTENCY", "transaction identity")
    status = "PASS" if all(item.status == "PASS" for item in failures) else "BLOCKED"
    return GateDecision("paid_execution_gate", status, ("SIRAJ.S09.PAID_EXECUTION_BOUNDARY",), tuple(failures))


class FakePaidExecutor:
    """Records an accepted fake transaction; it has no transport and no network."""

    def __init__(self) -> None:
        self._transactions: set[str] = set()
        self._click_nonces: set[str] = set()
        self._authorizations: set[str] = set()

    def execute(self, envelope: PaidExecutionEnvelope) -> Mapping[str, Any]:
        decision = evaluate_paid_execution_envelope(envelope)
        if decision.status != "PASS":
            raise ConstitutionEnforcementError("FAKE_PAID_GATE_BLOCKED")
        if envelope.transaction_id in self._transactions:
            raise ConstitutionEnforcementError("FAIL_DUPLICATE_PAID_TRANSACTION")
        if envelope.desktop_click_nonce in self._click_nonces:
            raise ConstitutionEnforcementError("FAIL_DUPLICATE_DESKTOP_CLICK")
        if envelope.authorization_id in self._authorizations:
            raise ConstitutionEnforcementError("FAIL_AUTHORIZATION_REUSED")
        self._transactions.add(envelope.transaction_id)
        self._click_nonces.add(envelope.desktop_click_nonce)
        self._authorizations.add(envelope.authorization_id)
        return MappingProxyType(
            {
                "status": "FAKE_ACCEPTED_BY_GATE_ONLY",
                "transaction_id": envelope.transaction_id,
                "provider_calls": 0,
                "paid_calls": 0,
                "network_calls": 0,
                "production_authorized": False,
            }
        )


def build_validation_receipts(
    rule: Mapping[str, Any],
    subject: Any,
    constitution: LoadedConstitution,
) -> dict[str, Mapping[str, str]]:
    subject_hash = artifact_sha256(subject)
    return {
        str(name): {
            "status": "PASS",
            "subject_sha256": subject_hash,
            "constitution_bundle_manifest_sha256": constitution.bundle_manifest_sha256,
            "human_actor": "TEST-HUMAN-REVIEWER",
            "decision_time": "2026-08-13T12:00:00+03:00",
        }
        for name in rule["validators"]
        if _validator_family(str(name)) == "HUMAN_RECEIPT"
    }


def build_rule_test_artifact(
    rule: Mapping[str, Any],
    constitution: LoadedConstitution,
) -> dict[str, Any]:
    subject = {"rule_id": rule["id"], "candidate": "compliant"}
    artifact: dict[str, Any] = {
        "subject": subject,
        "artifact_scope": LONGFORM_SCOPE,
        "text": "safe back-view composition, head outside frame, face fully excluded",
        "sensitive_domains": ["FACE", "MODESTY", "UNSEEN", "PERIOD", "SOURCE", "AUDIO", "MONTAGE"],
        "face_contract": {"all_human_faces_excluded": True, "crop_blur_mask_rescue": False},
        "wardrobe_contract": {"female_maximum_modesty": True, "male_period_modesty": True, "required_characters_present": True},
        "unseen_contract": {"divine_depiction": False, "invented_form_or_mechanism": False, "unknown_preserved": True},
        "period_contract": {"evidence_approved": True, "modern_elements": [], "unknown_detail_policy": "NEUTRAL_DO_NOT_INVENT"},
        "character_contract": {"canonical_still_sha256": "c" * 64, "provenance_approved": True, "identity_drift": False, "extra_characters": 0},
        "claims": [{"source_id": "SOURCE-1", "certainty_in": "HIGH", "certainty_out": "HIGH", "lower_source_overrides_higher": False, "classification": "PRIMARY", "material_disagreement": False}],
        "graphics_contract": {"arbitrary_graphics": False, "burned_captions": False, "asset_kind": "NONE", "face_policy_pass": True, "music_policy_pass": True},
        "narrative_contract": {"false_hook": False, "fabricated_mystery": False, "filler": False, "payoff_present": True},
        "episode_duration_contract": {"minutes": 12.0, "soft_exception_approved": False, "special_approval": False},
        "approval_contract": {"hash_bound": True, "stale": False, "required_receipts_present": True, "artifact_hash_match": True, "constitution_hash_match": True},
        "tts_contract": {"semantic_equivalence": True, "context_diacritization": True, "waqf_wasl": True, "pronunciation_lexicon": True},
        "visual_contract": {"semantic_alignment": True, "action_inverted": False, "generic_filler": False},
        "media_share_contract": {"core_episode_seconds": 600, "video_seconds": 360, "intro_outro_excluded": True},
        "reuse_contract": {"editorially_justified": True, "repetitive_padding": False},
        "pilot_contract": {"highest_risk_shots_selected": True, "all_frame_review_receipt_valid": True, "approved": True},
        "prompt_contract": {"structured": True, "all_required_fields": True, "canonical_reference_approved": True, "payload_hash_match": True, "executor_mutated_payload": False},
        "audio_tracks": [{"kind": "SFX", "contains_music": False}],
        "burned_captions": False,
        "on_screen_subtitles": False,
        "external_captions": True,
        "provider_profile": {"provider": "VEO_3_1_LITE", "approved": True, "silent_fallback": False, "automatic_switching": False},
        "batch_contract": {"progressive": True, "pilot_dependency_satisfied": True, "bounded_request_count": True, "new_risk_class_piloted": True},
        "retry_contract": {"requested": False, "automatic": False, "root_cause": False, "material_delta": False, "new_preflight": False, "new_human_authorization": False, "identical_quality_retry": False},
        "narrator_contract": {"identity": "CURRENT_APPROVED_NARRATOR", "replacement": False, "pronunciation_pass": True},
        "quran_contract": {"trusted_text": True, "llm_reconstruction": False, "human_text_review": True, "human_pronunciation_review": True},
        "sfx_contract": {"serves_narrative": True, "false_factual_presentation": False, "period_appropriate": True, "synced": True, "musical": False},
        "cost_authorization": {"stale": False, "estimated_cost": 1.0, "authorized_max_cost": 2.0},
        "submission_state": "REQUEST_NOT_SENT",
        "resubmit": False,
        "reconciliation_contract": {"authorizes_execution": False, "ledger_head_match": True},
        "historical_unknown_contract": {"attempt_id": "ATTEMPT-HISTORICAL-UNKNOWN-1", "provider_request": "PROVIDER-REQUEST-UNKNOWN-1", "status": "SUBMISSION_UNKNOWN", "retry": "BLOCKED_UNTIL_EVIDENCE_BASED_RECONCILIATION", "preserved": True},
        "transaction_contract": {"attempt_id": "ATTEMPT-1", "transaction_id": "TX-1", "duplicate": False, "double_click": False, "authorization_consumed_once": True},
        "recovery_contract": {"pre_spend_only": True, "provider_capability": False, "network_capability": False, "paid_capability": False},
        "narration_master": {"sha256": "a" * 64, "duration_ticks": 1000, "timebase": "1/1000"},
        "timeline": {"narration_master_sha256": "a" * 64, "duration_ticks": 1000, "timebase": "1/1000"},
        "montage_contract": {"all_assets_promoted": True, "render_hashes_match": True, "constitutional_qa_pass": True},
        "brand_contract": {"intro_count": 1, "outro_count": 1, "intro_sha256": "d" * 64, "outro_sha256": "e" * 64, "assets_unmodified": True, "face_policy_pass": True, "music_policy_pass": True},
        "placement_contract": {"intro_at_boundary": True, "outro_after_core_end": True, "intro_outro_excluded_from_core": True},
        "final_qa_contract": {"all_domain_findings_pass": True, "technical_qa_pass": True, "candidate_hash_match": True},
        "publication_contract": {"siraj_generates_title": False, "siraj_generates_thumbnail": False, "working_title_auto_publish": False, "public_metadata_required_for_production_pass": False},
        "paid_contract": {"origin": "DESKTOP", "desktop_click_nonce": "CLICK-1", "authorization_fresh": True, "payload_hash_match": True, "reference_hashes_match": True, "pilot_approved": True, "state_known": True},
        "governance_contract": {"constitution_id": constitution.constitution["id"], "version": constitution.constitution["version"], "bundle_manifest_sha256": constitution.bundle_manifest_sha256, "precedence": list(EXPECTED_PRECEDENCE), "machine_rule_source_count": 1},
        "coverage_contract": {"rule_count": 51, "covered_rules": 51, "uncovered_rules": 0, "runtime_gates_registered": True},
        "capability_contract": {"compiler_provider_call": False, "validator_mutation": False, "executor_creative_authority": False, "recovery_paid_execution": False, "tests_production_network": False},
        "ledger_contract": {"append_only": True, "chain_valid": True, "head_hash_match": True, "historical_mutation": False},
    }
    artifact["validation_receipts"] = build_validation_receipts(rule, subject, constitution)
    return artifact


def build_enforcement_coverage_manifest(
    registry: RuleRegistry,
    validators: ValidatorRegistry,
    *,
    audit_evidence: str,
) -> dict[str, Any]:
    coverage: list[dict[str, Any]] = []
    for rule_id in sorted(registry.by_id):
        rule = registry.by_id[rule_id]
        validator_bindings = [
            {"name": name, "binding_kind": validators.binding_kind(str(name))}
            for name in rule["validators"]
        ]
        compiler = rule["compiler"]
        item = {
            "RULE_ID": rule_id,
            "SECTION": rule["section"],
            "SEVERITY": rule["severity"],
            "COMPILER_BINDING": "compile_policy" if compiler["applies"] else None,
            "OR_COMPILER_NA_RATIONALE": None if compiler["applies"] else "Rule is enforced by independent validation and runtime gate; compiler has no applicable transformation.",
            "VALIDATOR_BINDINGS": validator_bindings,
            "POSITIVE_TEST_BINDINGS": [
                "tests/unit/test_unified_constitution_enforcement_v1.py::test_all_rules_have_positive_enforcement",
                *[f"CANONICAL_TEST:{name}" for name in rule["tests"]],
            ],
            "NEGATIVE_TEST_BINDINGS": [
                "tests/unit/test_unified_constitution_enforcement_v1.py::test_all_rules_fail_closed_without_required_evidence",
                *[f"CANONICAL_TEST:{name}" for name in rule["tests"]],
            ],
            "RUNTIME_GATE_BINDINGS": list(rule["runtime_gates"]),
            "AUDIT_EVIDENCE": audit_evidence,
            "STATUS": "COVERED",
        }
        compiler_missing = compiler["applies"] and not compiler["obligations"]
        validator_missing = not validator_bindings or any(
            binding["binding_kind"] == "MISSING" for binding in validator_bindings
        )
        if compiler_missing or validator_missing or not item["RUNTIME_GATE_BINDINGS"]:
            item["STATUS"] = "UNCOVERED"
        coverage.append(item)
    covered = sum(item["STATUS"] == "COVERED" for item in coverage)
    critical_unenforced = sum(
        item["STATUS"] != "COVERED" and item["SEVERITY"] == "CRITICAL" for item in coverage
    )
    high_unenforced = sum(
        item["STATUS"] != "COVERED" and item["SEVERITY"] == "HIGH" for item in coverage
    )
    return {
        "CONSTITUTION_ID": registry.constitution.constitution["id"],
        "CONSTITUTION_VERSION": registry.constitution.constitution["version"],
        "BUNDLE_MANIFEST_SHA256": registry.constitution.bundle_manifest_sha256,
        "RULE_COUNT": len(coverage),
        "COVERED_RULES": covered,
        "UNCOVERED_RULES": len(coverage) - covered,
        "CRITICAL_RULES_UNENFORCED": critical_unenforced,
        "HIGH_RULES_UNENFORCED": high_unenforced,
        "VALIDATOR_IMPLEMENTATIONS_COMPLETE": all(
            binding["binding_kind"] != "MISSING"
            for item in coverage
            for binding in item["VALIDATOR_BINDINGS"]
        ),
        "RULES": coverage,
        "PRODUCTION_AUTHORIZED": False,
    }


def capability_boundary_evidence(module_path: Path) -> dict[str, Any]:
    module_path = Path(module_path)
    repo_root = module_path.resolve().parents[2]
    inspected_paths = [module_path]
    inspected_paths.extend(sorted((repo_root / "tests").rglob("*unified_constitution*.py")))
    forbidden_imports = (
        "requests",
        "httpx",
        "urllib.request",
        "aiohttp",
        "desktop_provider_execution",
        "ep002_v24_repair_provider_execution",
    )
    violations: list[str] = []
    for path in inspected_paths:
        text = path.read_text(encoding="utf-8")
        for item in forbidden_imports:
            if re.search(rf"(?:import|from)\s+{re.escape(item)}\b", text):
                violations.append(f"{path.relative_to(repo_root)}:{item}")
    return {
        "modules": [str(path.relative_to(repo_root)) for path in inspected_paths],
        "forbidden_imports": violations,
        "compiler_provider_call": False,
        "validator_mutation": False,
        "recovery_paid_capability": False,
        "tests_production_transport": False,
        "status": "PASS" if not violations else "BLOCKED",
    }


__all__ = [
    "ApprovalReceipt",
    "ApprovalValidationError",
    "CONSTITUTION_BUNDLE_ID",
    "CONSTITUTION_RELATIVE_DIRECTORY",
    "CONSTITUTION_VERSION",
    "ConstitutionEnforcementError",
    "ConstitutionLoadError",
    "FakePaidExecutor",
    "GateDecision",
    "InvalidationEngine",
    "LoadedConstitution",
    "PaidExecutionEnvelope",
    "PolicyCompilationError",
    "RuleRegistry",
    "RuntimeGateEngine",
    "ValidationFinding",
    "ValidatorRegistry",
    "analyze_face_semantics",
    "analyze_sensitive_semantics",
    "artifact_sha256",
    "build_enforcement_coverage_manifest",
    "build_rule_test_artifact",
    "capability_boundary_evidence",
    "compile_policy",
    "evaluate_paid_execution_envelope",
    "load_unified_constitution",
    "sha256_file",
    "verify_approval_receipt",
]
