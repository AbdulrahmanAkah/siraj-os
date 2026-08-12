"""SIRAJ V6.3 generic upstream pipeline for future episodes.

Seven stages:
TOPIC_SELECTION
SOURCE_RESEARCH_FROM_ZERO
SOURCE_CLAIM_MATRIX
STORY_ARCHITECTURE
ICONIC_CINEMATIC_REVIEW
FINAL_SCRIPT
PRONUNCIATION_AND_PERFORMANCE_GATE

All stages are reusable for every future episode and are independent from
Episode 002's already-completed preproduction.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping
import unicodedata

from src.application.shamela_primary_research_v1 import (
    build_shamela_primary_context,
)
from src.application.siraj_luna_upstream_transport_v6_3 import (
    execute_authorized_stage,
)

FIXED_CTA_AR = (
    "إذا أعجبك هذا المحتوى، اشترك في سراج، وتابع معنا بقية الرحلة."
)

ARABIC_MARKS = {
    "\u064b", "\u064c", "\u064d",
    "\u064e", "\u064f", "\u0650",
    "\u0651", "\u0652", "\u0670",
}
ARABIC_WORD_RE = re.compile(r"[\u0621-\u064a\u066e-\u06d3\u064b-\u0652\u0670]+")


class UpstreamV63Error(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise UpstreamV63Error("JSON_OBJECT_REQUIRED:" + str(path))
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(tmp, path)


def _series_catalog(repo: Path) -> list[dict[str, Any]]:
    projects = repo / "projects"
    result: list[dict[str, Any]] = []
    if not projects.is_dir():
        return result

    for episode in sorted(projects.glob("episode-*")):
        if not episode.is_dir():
            continue
        candidates = [
            episode / "contracts/episode-definition-v1.json",
            episode / "preproduction/luna-story-architecture-v5.json",
            episode / "preproduction/luna-final-script-v5-1.json",
            episode / "research/luna-research-final-v4.json",
        ]
        title = ""
        summary = ""
        for path in candidates:
            if not path.is_file():
                continue
            try:
                payload = _read(path)
            except Exception:
                continue
            title = str(
                payload.get("title_ar")
                or payload.get("working_title_ar")
                or payload.get("topic_title_ar")
                or payload.get("title")
                or title
            )
            summary = str(
                payload.get("episode_summary_ar")
                or payload.get("research_summary_ar")
                or payload.get("summary_ar")
                or summary
            )
            if title and summary:
                break
        result.append(
            {
                "episode_id": episode.name,
                "title_ar": title,
                "summary_ar": summary[:1200],
            }
        )
    return result


def next_episode_number(repo_root: Path) -> int:
    repo = Path(repo_root).resolve()
    numbers = []
    for path in (repo / "projects").glob("episode-*"):
        match = re.match(r"episode-(\d+)", path.name)
        if match:
            numbers.append(int(match.group(1)))
    return (max(numbers) + 1) if numbers else 1


def topic_selection_input(repo_root: Path) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    return {
        "task": "SELECT_NEXT_SIRAJ_EPISODE_TOPIC",
        "next_episode_number": next_episode_number(repo),
        "existing_episode_catalog": _series_catalog(repo),
        "series_law": {
            "automatic_topic_selection": True,
            "avoid_repeating_completed_topics": True,
            "fresh_research_required_after_selection": True,
            "sources_before_script": True,
            "religious_historical_fidelity": True,
            "music": "FORBIDDEN",
            "media_mix_policy": "SIRAJ_CINEMATIC_MEDIA_MIX_POLICY_V2",
            "generated_video_min_ratio": 0.50,
            "generated_video_max_ratio": 0.75,
            "no_fixed_episode_duration": True,
            "no_fixed_event_count": True,
            "no_fixed_scene_count": True,
        },
    }


def run_topic_selection(
    repo_root: Path,
    bootstrap_episode_id: str,
) -> Path:
    repo = Path(repo_root).resolve()
    payload = topic_selection_input(repo)
    system = """
أنت Luna، العقل المركزي لسراج: الباحث الرئيس، المحرر، مهندس السرد،
والمخرج السينمائي. تعمل في وضع MAX/PRO.

اختر موضوع الحلقة التالية تلقائيًا. لا تكرر موضوعًا غطته حلقة مكتملة،
ولا تختَر موضوعًا لمجرد سهولة الإنتاج. اختر أفضل استمرار معرفي وسردي
للسلسلة، مع قابلية بحث قوية ومادة بصرية غنية.

هذه مرحلة اختيار الموضوع فقط؛ لا تكتب السيناريو ولا تختلق المصادر.
أخرج JSON فقط، ويجب أن يتضمن:
status=PASS، episode_number، slug_en، topic_title_ar، working_title_ar،
central_question_ar، episode_promise_ar، selection_rationale_ar،
research_queries، source_priority_notes_ar، known_risks_ar.
لا تضع مدة ثابتة للحلقة ولا عددًا ثابتًا للأحداث أو المشاهد.
"""
    return execute_authorized_stage(
        repo,
        bootstrap_episode_id,
        "TOPIC_SELECTION",
        system_prompt=system,
        input_payload=payload,
        output_path_relative="preproduction/topic-selection-v6-3.json",
        use_web_search=False,
    )


def materialize_selected_episode(
    repo_root: Path,
    bootstrap_episode_id: str,
) -> tuple[str, Path]:
    repo = Path(repo_root).resolve()
    selection_path = (
        repo
        / "projects"
        / bootstrap_episode_id
        / "preproduction/topic-selection-v6-3.json"
    )
    selection = _read(selection_path)
    if selection.get("status") != "PASS":
        raise UpstreamV63Error("TOPIC_SELECTION_NOT_PASS")

    number = int(selection.get("episode_number", 0) or 0)
    slug = str(selection.get("slug_en") or "").strip()
    if number <= 0 or not re.fullmatch(
        r"[a-z0-9]+(?:-[a-z0-9]+)*",
        slug,
    ):
        raise UpstreamV63Error("TOPIC_SELECTION_IDENTITY_INVALID")

    episode_id = f"episode-{number:03d}-{slug}"
    target = repo / "projects" / episode_id
    if target.exists():
        raise UpstreamV63Error(
            "SELECTED_EPISODE_DIRECTORY_ALREADY_EXISTS:" + episode_id
        )
    target.mkdir(parents=True)
    for child in (
        "contracts",
        "research",
        "preproduction",
        "orchestration",
        "audio",
        "cinematic",
        "deliverables",
    ):
        (target / child).mkdir(parents=True, exist_ok=True)

    contract = {
        "schema_version": "siraj-episode-definition-v6.3",
        "status": "ACTIVE",
        "episode_id": episode_id,
        "episode_number": number,
        "slug_en": slug,
        "topic_title_ar": selection.get("topic_title_ar"),
        "working_title_ar": selection.get("working_title_ar"),
        "central_question_ar": selection.get("central_question_ar"),
        "episode_promise_ar": selection.get("episode_promise_ar"),
        "selection_rationale_ar": selection.get("selection_rationale_ar"),
        "research_queries": selection.get("research_queries") or [],
        "source_priority_notes_ar": selection.get(
            "source_priority_notes_ar"
        )
        or [],
        "created_at_utc": _now(),
        "pipeline_origin": "SIRAJ_V6_3_AUTOPILOT",
    }
    _write(
        target / "contracts/episode-definition-v6-3.json",
        contract,
    )
    # Preserve the paid selection artifact in the canonical new episode.
    _write(
        target / "preproduction/topic-selection-v6-3.json",
        selection,
    )
    return episode_id, target


def source_research_input(
    repo_root: Path,
    episode_id: str,
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    ep = repo / "projects" / episode_id
    definition = _read(
        ep / "contracts/episode-definition-v6-3.json"
    )
    local_context = build_shamela_primary_context(
        repo,
        definition,
        require_excerpts=True,
    )
    return {
        "task": "FRESH_SOURCE_RESEARCH_FROM_ZERO",
        "episode_definition": definition,
        "source_priority": {
            "quran_and_authentic_hadith": "PRIMARY_WHEN_APPLICABLE",
            "selected_shamela_sources": "PRIMARY_CLASSICAL_CORPUS",
            "web": "SECONDARY_GAP_FILL_AND_VERIFICATION",
        },
        "local_shamela_context": local_context,
        "research_law": {
            "do_not_reuse_previous_episode_research_as_evidence": True,
            "previous_episodes_may_only_prevent_topic_duplication": True,
            "source_locator_or_url_required": True,
            "separate_fact_from_report_from_editorial_bridge": True,
            "weak_or_disputed_material_must_be_qualified_or_excluded": True,
            "fresh_web_search_allowed_for_gaps": True,
            "no_script_writing_in_this_stage": True,
        },
    }


def run_source_research(
    repo_root: Path,
    episode_id: str,
) -> Path:
    repo = Path(repo_root).resolve()
    payload = source_research_input(repo, episode_id)
    system = """
أنت Luna الباحث الرئيس لسراج في وضع MAX/PRO.
ابدأ البحث من الصفر لهذه الحلقة. المادة المحلية من الشاملة هي corpus أولي،
والويب مسموح لسد الفجوات والتحقق والوصول إلى مصادر موثوقة.

لا تكتب السيناريو. لا تستخدم موضوعات أو أبحاث حلقات سابقة كدليل.
استخرج ما يدعم أو يضعف كل قضية مع provenance قابل للمراجعة.

أخرج JSON فقط ويجب أن يتضمن:
status=PASS
research_summary_ar
source_register[]
research_findings[]
candidate_claims[]
chronology_candidates[]
contradictions_and_disputes[]
excluded_material[]
research_gaps[]
web_gap_searches[]
self_review

كل source_register item يجب أن يحمل source_id وtitle وsource_type
وauthor_or_publisher وlocator_or_url وreliability_assessment_ar.
كل candidate_claim يجب أن يرتبط بمعرفات مصادر فعلية.
عند القرآن والحديث لا تخترع نصًا أو إحالة.
لا تضع حدًا ثابتًا لعدد المصادر أو الادعاءات أو جولات التفكير.
"""
    return execute_authorized_stage(
        repo,
        episode_id,
        "SOURCE_RESEARCH_FROM_ZERO",
        system_prompt=system,
        input_payload=payload,
        output_path_relative="research/source-research-from-zero-v6-3.json",
        use_web_search=True,
    )


def run_source_claim_matrix(
    repo_root: Path,
    episode_id: str,
) -> Path:
    repo = Path(repo_root).resolve()
    research = _read(
        repo
        / "projects"
        / episode_id
        / "research/source-research-from-zero-v6-3.json"
    )
    payload = {
        "task": "BUILD_CANONICAL_SOURCE_CLAIM_MATRIX",
        "research": research,
        "law": {
            "every_allowed_claim_requires_traceable_source_ids": True,
            "no_source_invention": True,
            "exclude_unsupported_material": True,
            "qualification_required_for_disputed_material": True,
            "canonical_events_must_be_claim_backed": True,
        },
    }
    system = """
أنت Luna، محرر الأدلة في سراج. حوّل البحث الطازج إلى Source Claim Matrix
مرجعية قبل أي بناء قصصي.

أخرج JSON فقط مع:
status=PASS
canonical_sources[]
claims[]
events[]
excluded_material[]
research_gaps[]
matrix_self_review

لكل claim:
claim_id، claim_ar، evidence_posture، confidence، source_ids،
use_policy(ALLOWED/QUALIFIED_ONLY/EXCLUDED)، qualification_ar.
ولكل event قائمة claim_ids موثقة.
لا تضف حقيقة غير موجودة في حزمة البحث.
"""
    return execute_authorized_stage(
        repo,
        episode_id,
        "SOURCE_CLAIM_MATRIX",
        system_prompt=system,
        input_payload=payload,
        output_path_relative="research/source-claim-matrix-v6-3.json",
        use_web_search=False,
    )


def run_story_architecture(
    repo_root: Path,
    episode_id: str,
) -> Path:
    repo = Path(repo_root).resolve()
    ep = repo / "projects" / episode_id
    definition = _read(
        ep / "contracts/episode-definition-v6-3.json"
    )
    matrix = _read(
        ep / "research/source-claim-matrix-v6-3.json"
    )
    payload = {
        "task": "DESIGN_STORY_ARCHITECTURE",
        "episode_definition": definition,
        "source_claim_matrix": matrix,
        "creative_law": {
            "truth_before_drama": True,
            "no_fixed_act_count": True,
            "no_fixed_beat_count": True,
            "no_fixed_duration": True,
            "build_cinematic_causality": True,
            "one_memorable_visual_idea_per_major_beat": True,
        },
    }
    system = """
أنت Luna: Showrunner + Narrative Architect لسراج، وضع MAX/PRO.
ابنِ أفضل هندسة قصصية ممكنة من الادعاءات المسموح بها فقط.

لا توجد مدة مفروضة، ولا عدد ثابت للأفعال أو beats. استخدم ما يحتاجه
الموضوع فقط. اجعل كل beat يغيّر فهمًا أو ضغطًا أو سؤالًا أو اتجاهًا.
احفظ dignity والضبط الديني، ولا تخترع تفاصيل غيبية.

أخرج JSON فقط مع:
status=PASS
narrative_thesis_ar
acts[]
beats[]
motifs[]
continuity_anchors[]
source_truth_constraints[]
architecture_self_review
وكل beat يحمل beat_id وclaim_ids ووظيفته الدرامية وما ينبغي أن يفهمه
المشاهد وما الفكرة البصرية المميزة التي يمكن أن تخدمه.
"""
    return execute_authorized_stage(
        repo,
        episode_id,
        "STORY_ARCHITECTURE",
        system_prompt=system,
        input_payload=payload,
        output_path_relative="preproduction/story-architecture-v6-3.json",
        use_web_search=False,
    )


def run_iconic_cinematic_review(
    repo_root: Path,
    episode_id: str,
) -> Path:
    repo = Path(repo_root).resolve()
    ep = repo / "projects" / episode_id
    architecture = _read(
        ep / "preproduction/story-architecture-v6-3.json"
    )
    matrix = _read(
        ep / "research/source-claim-matrix-v6-3.json"
    )
    payload = {
        "task": "ICONIC_CINEMATIC_MAX_REVIEW",
        "architecture": architecture,
        "source_claim_matrix": matrix,
    }
    system = """
أنت Luna في أقصى وضع سينمائي MAX/PRO: Showrunner ومخرج ومصور ومحرر.
راجع هندسة القصة نقديًا وأعد نسخة أفضل منها، لا مجرد تقرير نقد.

اختباراتك:
- iconic first بلا استعراض زائد
- causal cinematic progression
- silent-frame test
- scale / foreground-midground-background / lens logic
- motivated camera movement
- light/material/color continuity
- emotional precision and rhythm
- anti-generic-AI visual thinking
- no artist imitation
- no invented theology or literal depiction of the unseen
- every beat remains traceable to allowed claim IDs

أخرج JSON فقط:
status=PASS
reviewed_architecture{...}
changes_made[]
remaining_constraints[]
max_pro_self_review
ولا تمرر PASS إلا إذا أصبحت reviewed_architecture هي النسخة التي تريد
فعلاً إنتاجها.
"""
    return execute_authorized_stage(
        repo,
        episode_id,
        "ICONIC_CINEMATIC_REVIEW",
        system_prompt=system,
        input_payload=payload,
        output_path_relative=(
            "preproduction/story-architecture-iconic-reviewed-v6-3.json"
        ),
        use_web_search=False,
    )


def run_final_script(
    repo_root: Path,
    episode_id: str,
) -> Path:
    repo = Path(repo_root).resolve()
    ep = repo / "projects" / episode_id
    review = _read(
        ep / "preproduction/story-architecture-iconic-reviewed-v6-3.json"
    )
    matrix = _read(
        ep / "research/source-claim-matrix-v6-3.json"
    )
    definition = _read(
        ep / "contracts/episode-definition-v6-3.json"
    )
    payload = {
        "task": "WRITE_FINAL_SCRIPT",
        "episode_definition": definition,
        "source_claim_matrix": matrix,
        "iconic_review": review,
        "fixed_series_cta_excluded_from_script": FIXED_CTA_AR,
        "script_law": {
            "no_fixed_word_count": True,
            "no_fixed_segment_count": True,
            "no_fixed_duration": True,
            "exact_claim_traceability": True,
            "exact_beat_traceability": True,
            "qualified_claims_keep_qualification": True,
            "cta_is_separate_reusable_asset": True,
        },
    }
    system = """
أنت Luna الكاتب النهائي لسراج في وضع MAX/PRO.
اكتب النص العربي النهائي القابل للأداء الصوتي اعتمادًا حصريًا على
Source Claim Matrix والهندسة السينمائية المراجعة.

لا يوجد عدد كلمات أو مقاطع أو مدة محددة. دع القصة والمادة الموثقة تحددان
الطول. كل segment يجب أن يحمل segment_id وbeat_ids وclaim_ids وsource_ids.
لا تستخدم EXCLUDED، وQUALIFIED_ONLY يجب أن يبقى مؤهلاً في اللغة.
لا تحول النص إلى محاضرة، ولا تضف ادعاءات لزيادة الدراما.
لا تضمّن CTA الثابت؛ فهو أصل منفصل.

أخرج JSON فقط مع:
status=PASS
title_ar (يجوز null إذا لم يحسم)
segments[]
pronunciation_candidates[]
script_self_review
كل segment يحتوي order، segment_id، narration_ar، beat_ids، claim_ids،
source_ids، performance_intent_ar، pause_intent_after.
"""
    output = execute_authorized_stage(
        repo,
        episode_id,
        "FINAL_SCRIPT",
        system_prompt=system,
        input_payload=payload,
        output_path_relative="preproduction/final-script-v6-3.json",
        use_web_search=False,
    )

    result = _read(output)
    segments = result.get("segments")
    if not isinstance(segments, list) or not segments:
        raise UpstreamV63Error("FINAL_SCRIPT_SEGMENTS_REQUIRED")
    narration = "\n\n".join(
        str(segment.get("narration_ar") or "").strip()
        for segment in segments
        if isinstance(segment, Mapping)
    ).strip()
    if not narration:
        raise UpstreamV63Error("FINAL_SCRIPT_NARRATION_EMPTY")
    (
        repo
        / "projects"
        / episode_id
        / "preproduction/final-narration-ar-v6-3.txt"
    ).write_text(narration + "\n", encoding="utf-8")
    return output


def _strip_arabic_marks(text: str) -> str:
    return "".join(
        ch
        for ch in unicodedata.normalize("NFC", text)
        if unicodedata.combining(ch) == 0
        and ch not in ARABIC_MARKS
    )


def _lexical_normalize(text: str) -> str:
    value = _strip_arabic_marks(text)
    value = value.replace("آ", "ا")
    value = value.replace("أ", "ا").replace("إ", "ا")
    value = value.replace("ٱ", "ا")
    value = value.replace("ؤ", "و").replace("ئ", "ي")
    value = re.sub(r"[^\u0621-\u064a\u066e-\u06d3]+", " ", value)
    return " ".join(value.split())


CORE_VOWEL_MARKS = {
    "\u064b",  # fathatan
    "\u064c",  # dammatan
    "\u064d",  # kasratan
    "\u064e",  # fatha
    "\u064f",  # damma
    "\u0650",  # kasra
    "\u0652",  # sukun
    "\u0670",  # dagger alif
}
FATHA_LIKE_MARKS = {"\u064e", "\u064b", "\u0670"}
DAMMA_LIKE_MARKS = {"\u064f", "\u064c"}
KASRA_LIKE_MARKS = {"\u0650", "\u064d"}
MADD_COMBINING_MARK = "\u0653"


def _arabic_clusters(word: str) -> list[tuple[str, set[str]]]:
    normalized = unicodedata.normalize("NFD", word)
    clusters: list[list[Any]] = []
    for character in normalized:
        if unicodedata.combining(character):
            if clusters:
                clusters[-1][1].add(character)
            continue
        clusters.append([character, set()])
    return [
        (str(base), set(marks))
        for base, marks in clusters
    ]


def _strong_vocalization_errors(word: str) -> list[str]:
    """Return missing-pronunciation carriers in one Arabic word.

    "Full pronunciation-oriented diacritization" is stronger than merely
    finding *one* mark somewhere in a word.  Every consonantal carrier must
    have an explicit short vowel/tanween/sukun/dagger-alif, except for
    deterministic long-vowel carriers and hamzat-wasl/article carriers.

    Madda (آ) is treated as a self-vocalized carrier, matching the V5.3.1
    lexical-normalization law.
    """
    clusters = _arabic_clusters(word)
    missing: list[str] = []

    for index, (base, marks) in enumerate(clusters):
        # NFD turns آ into bare alef + COMBINING MADDA ABOVE.
        if MADD_COMBINING_MARK in marks:
            continue

        # Explicit hamzat wasl is a pronunciation carrier by itself.
        if index == 0 and base == "\u0671":
            continue

        # The bare carrier in the Arabic definite article is valid when the
        # lam itself carries its pronunciation mark.
        if (
            index == 0
            and base == "\u0627"
            and len(clusters) >= 2
            and clusters[1][0] == "\u0644"
        ):
            continue

        previous_marks = (
            clusters[index - 1][1]
            if index > 0
            else set()
        )

        # Long vowels do not take an independent short-vowel mark.
        if (
            base == "\u0627"
            and index > 0
            and previous_marks & FATHA_LIKE_MARKS
        ):
            continue
        if (
            base == "\u0648"
            and index > 0
            and previous_marks & DAMMA_LIKE_MARKS
        ):
            continue
        if (
            base == "\u064a"
            and index > 0
            and previous_marks & KASRA_LIKE_MARKS
        ):
            continue
        if (
            base == "\u0649"
            and index > 0
            and previous_marks & FATHA_LIKE_MARKS
        ):
            continue

        # Shadda alone is not enough: the consonant still needs its actual
        # vowel/sukun carrier for reliable TTS pronunciation.
        if not (marks & CORE_VOWEL_MARKS):
            missing.append(base)

    return missing


def validate_tts_segment(
    source_text: str,
    tts_text: str,
    aliases: list[Mapping[str, Any]] | None = None,
) -> list[str]:
    errors: list[str] = []
    if "#" in tts_text or "*" in tts_text or "`" in tts_text:
        errors.append("TTS_MARKUP_FORBIDDEN")

    source_for_compare = source_text
    spoken_for_compare = tts_text

    for alias in aliases or []:
        if not isinstance(alias, Mapping):
            continue
        source = str(alias.get("source_form") or "")
        spoken = str(alias.get("spoken_form") or "")
        reason = str(alias.get("reason") or "")
        if not source or not spoken or reason != "QURAN_DISJOINT_LETTERS":
            errors.append("PRONUNCIATION_ALIAS_INVALID")
            continue
        source_for_compare = source_for_compare.replace(source, spoken)

    if _lexical_normalize(source_for_compare) != _lexical_normalize(
        spoken_for_compare
    ):
        errors.append("TTS_LEXICAL_CONTENT_CHANGED")

    for word in ARABIC_WORD_RE.findall(tts_text):
        bare = _strip_arabic_marks(word)
        if len(bare) < 2:
            continue

        missing = _strong_vocalization_errors(word)
        if missing:
            errors.append(
                "BARE_MULTI_LETTER_ARABIC_WORD:"
                + word
                + ":MISSING_CARRIERS="
                + "".join(missing)
            )

    return errors

def run_pronunciation_performance_gate(
    repo_root: Path,
    episode_id: str,
) -> Path:
    repo = Path(repo_root).resolve()
    ep = repo / "projects" / episode_id
    script = _read(
        ep / "preproduction/final-script-v6-3.json"
    )
    payload = {
        "task": "FULL_ARABIC_PRONUNCIATION_AND_PERFORMANCE_GATE",
        "final_script": script,
        "global_pronunciation_law": {
            "scope": "ALL_EPISODES_LEGACY_AND_FUTURE",
            "full_pronunciation_oriented_diacritization": True,
            "selective_only_diacritization": "FORBIDDEN",
            "bare_multi_letter_arabic_word_in_tts": "FORBIDDEN",
            "lexical_script_rewrite": "FORBIDDEN",
            "pause_aware_endings": True,
            "quran_direct_quote_prefers_canonical_vocalization": True,
            "hadith_direct_quote_preserve_wording": True,
            "madda_is_self_vocalized_carrier": True,
        },
    }
    system = """
أنت Luna محرر النطق والأداء في سراج.
حوّل كل narration_ar إلى tts_text_ar مشكول تشكيلًا نطقيًا كاملاً يقلل أخطاء
TTS. لا تغيّر أي كلمة أو معنى أو ترتيب ألفاظ السيناريو.

المطلوب ليس إعرابًا مدرسياً آلياً عند الوقف، بل نطق عربي صحيح:
حركات/شدة/سكون على مواضع النطق، وضوح الأسماء واللفظ الملتبس، وهمزات
الوصل والقطع حيث تؤثر، ونهايات وقف طبيعية حتى لا يبالغ TTS في الإعراب.

إذا احتاجت الحروف المقطعة في القرآن صيغة نطق تختلف كتابيًا، ضع alias صريحًا
في pronunciation_aliases مع reason=QURAN_DISJOINT_LETTERS. لا تستخدم
aliases لأي إعادة كتابة أخرى.

لا Markdown داخل tts_text_ar.

أخرج JSON فقط:
status=PASS
segments[]
pronunciation_self_review

كل segment يجب أن يحمل:
segment_id
source_narration_ar (نسخة مطابقة حرفياً من narration_ar)
tts_text_ar
pause_after_seconds
performance_direction_ar
pronunciation_aliases[]
"""
    output = execute_authorized_stage(
        repo,
        episode_id,
        "PRONUNCIATION_AND_PERFORMANCE_GATE",
        system_prompt=system,
        input_payload=payload,
        output_path_relative=(
            "preproduction/pronunciation-performance-gate-v6-3.json"
        ),
        use_web_search=False,
    )

    result = _read(output)
    generated = result.get("segments")
    original = script.get("segments")
    if not isinstance(generated, list) or not isinstance(original, list):
        raise UpstreamV63Error("PRONUNCIATION_SEGMENTS_REQUIRED")

    original_by_id = {
        str(segment.get("segment_id")): segment
        for segment in original
        if isinstance(segment, Mapping)
    }
    errors = []
    tts_blocks = []

    for segment in generated:
        if not isinstance(segment, Mapping):
            errors.append("PRONUNCIATION_SEGMENT_OBJECT_REQUIRED")
            continue
        segment_id = str(segment.get("segment_id") or "")
        source = original_by_id.get(segment_id)
        if source is None:
            errors.append("UNKNOWN_PRONUNCIATION_SEGMENT:" + segment_id)
            continue
        source_text = str(source.get("narration_ar") or "")
        echoed = str(segment.get("source_narration_ar") or "")
        tts_text = str(segment.get("tts_text_ar") or "")
        if echoed != source_text:
            errors.append("SOURCE_NARRATION_ECHO_CHANGED:" + segment_id)
        errors.extend(
            segment_id + ":" + error
            for error in validate_tts_segment(
                source_text,
                tts_text,
                list(segment.get("pronunciation_aliases") or []),
            )
        )
        if tts_text.strip():
            tts_blocks.append(tts_text.strip())

    if len(generated) != len(original):
        errors.append(
            "PRONUNCIATION_SEGMENT_COUNT_MISMATCH:"
            f"{len(generated)}:{len(original)}"
        )

    audit = {
        "schema_version": "siraj-pronunciation-audit-v6.3",
        "status": "PASS" if not errors else "FAIL",
        "episode_id": episode_id,
        "error_count": len(errors),
        "errors": errors,
        "full_diacritization_strong_audit": (
            "PASS" if not errors else "FAIL"
        ),
        "tts_markup_gate": "PASS" if not any(
            "MARKUP" in error for error in errors
        ) else "FAIL",
        "lexical_equivalence_gate": "PASS" if not any(
            "LEXICAL" in error or "ECHO_CHANGED" in error
            for error in errors
        ) else "FAIL",
        "global_pronunciation_law": "V6.3_ACTIVE",
    }
    _write(
        ep / "orchestration/pronunciation-audit-v6-3.json",
        audit,
    )
    if errors:
        raise UpstreamV63Error(
            "PRONUNCIATION_GATE_LOCAL_AUDIT_FAILED:"
            + "|".join(errors[:20])
        )

    (
        ep / "preproduction/final-narration-tts-ready-ar-v6-3.txt"
    ).write_text(
        "\n\n".join(tts_blocks) + "\n",
        encoding="utf-8",
    )
    return output
