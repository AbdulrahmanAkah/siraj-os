"""Evidence-aware Episode 01 concept preproduction; no media generation."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile
from typing import Any

from src.application.operations_common import CANONICAL_TIMESTAMP, deterministic_id
from src.application.project_runtime import load_project, project_paths


CONCEPTS_SCHEMA = "siraj-episode-01-concepts-v4"
REPORT_SCHEMA = "siraj-episode-01-preproduction-report-v4"


def _write(path: Path, content: str, *, replace: bool) -> None:
    if path.exists() and not replace:
        raise FileExistsError(f"ARTIFACT_EXISTS:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(content)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _concept(
    concept_id: str,
    title: str,
    central_idea: str,
    hook: str,
    audience: str,
    duration: str,
    story: list[str],
    claim_ids: list[str],
    assets: list[str],
    image_ratio: int,
    motion_ratio: int,
    risks: list[str],
) -> dict[str, Any]:
    return {
        "concept_id": concept_id,
        "temporary_title": title,
        "central_idea": central_idea,
        "hook_first_10_seconds": hook,
        "target_audience": audience,
        "proposed_duration": duration,
        "story_structure": story,
        "required_historical_claim_ids": claim_ids,
        "visual_asset_types": assets,
        "visual_mix_percent": {"still_images": image_ratio, "moving_footage_or_motion_design": motion_ratio},
        "research_and_production_risks": risks,
        "selection_status": "USER_SELECTION_REQUIRED",
    }


def build_episode_01_preproduction(project_root: str | Path, *, replace: bool = False) -> dict[str, Any]:
    root = Path(project_root).resolve(strict=False)
    load_project(root)
    paths = project_paths(root)
    claims_payload = json.loads((Path(paths.working_root) / "knowledge" / "claims.json").read_text(encoding="utf-8-sig"))
    gaps_payload = json.loads((Path(paths.working_root) / "assessment" / "research-gaps.json").read_text(encoding="utf-8-sig"))
    tasks_payload = json.loads((Path(paths.working_root) / "research" / "research-tasks.json").read_text(encoding="utf-8-sig"))
    sources_payload = json.loads((root / "sources.json").read_text(encoding="utf-8-sig"))
    claims = claims_payload.get("claims", [])
    claim_for = {item["claim_text"]: item["claim_id"] for item in claims if isinstance(item, dict) and item.get("claim_text") and item.get("claim_id")}
    required_text = (
        "Baghdad became a major center of learning.",
        "The Tigris River flows through Baghdad.",
        "The Abbasid caliph Al-Mansur founded Baghdad.",
        "Baghdad was founded in the year 762.",
        "Baghdad is the capital of Iraq.",
        "The House of Wisdom operated in Baghdad.",
    )
    if any(text not in claim_for for text in required_text):
        raise ValueError("EPISODE_01_REQUIRED_BAGHDAD_CLAIMS_MISSING")
    founding = [claim_for[required_text[2]], claim_for[required_text[3]], claim_for[required_text[1]], claim_for[required_text[4]]]
    river = [claim_for[required_text[1]], claim_for[required_text[2]], claim_for[required_text[3]], claim_for[required_text[4]]]
    knowledge = [claim_for[required_text[0]], claim_for[required_text[5]], claim_for[required_text[2]], claim_for[required_text[3]]]
    concepts = [
        _concept(
            "episode01_concept_city_decision",
            "بغداد: المدينة التي بدأت بقرار",
            "تبدأ الحلقة من لحظة تأسيس بغداد سنة 762، ثم تنتقل من قرار المنصور إلى مدينةٍ يصنع موقعها على دجلة صورتها المعاصرة.",
            "لقطة بغداد الليلية من فوق دجلة، ثم سؤال مباشر: كيف يبدأ تاريخ مدينةٍ بقرار واحد؟",
            "مشاهد عربي عام من 18 إلى 40 عاماً، مهتم بالتاريخ الحضري والقصص القصيرة السينمائية.",
            "8–10 دقائق",
            ["افتتاح بصري من بغداد المعاصرة", "العودة إلى 762 وتأسيس المنصور", "دجلة بوصفه محور المكان", "العودة إلى بغداد عاصمة العراق وخاتمة تفتح باب الحلقة التالية"],
            founding,
            ["لقطات مدينة معاصرة", "خريطة دجلة وبغداد", "إعادة بناء عباسية معلنة", "صورة أو إعادة بناء للمنصور", "مقاطع نهرية", "وثائق تأسيس أو خرائط مرخصة"],
            45,
            55,
            ["كل claims الحالية ذات دعم مصدر واحد؛ يلزم corroboration مستقل قبل النص النهائي.", "يحتاج التأسيس وسياق اختيار الموقع إلى مصادر أولية أو أكاديمية إضافية.", "يتطلب الإنتاج مزيجاً من لقطات بغداد المرخصة وإعادات بناء معلنة بوضوح."],
        ),
        _concept(
            "episode01_concept_river_memory",
            "دجلة: النهر الذي يمرّ في قلب بغداد",
            "تُروى الحلقة عبر دجلة: من نهر يمر في المدينة إلى خيط بصري يصل بغداد العباسية بعاصمتها المعاصرة.",
            "صوت ماء هادئ فوق لقطة شروق، ثم الجملة: قبل أن نصل إلى بغداد، يصل إلينا دجلة أولاً.",
            "مشاهد عربي يفضّل السرد الحسي والسفر التاريخي البصري، من 18 إلى 45 عاماً.",
            "7–9 دقائق",
            ["افتتاح من سطح الماء", "خريطة تبين مرور دجلة", "انتقال إلى تأسيس بغداد", "محطات بصرية بين النهر والمدينة", "خاتمة ليلية على ضفافه"],
            river,
            ["لقطات دجلة متحركة", "خرائط تاريخية وحديثة", "لقطات جوية لبغداد", "إعادة بناء المدينة العباسية", "لقطات ضفاف ومراكب", "خرائط طبوغرافية مرخصة"],
            30,
            70,
            ["الادعاء المتاح يثبت مرور دجلة فقط؛ لا يثبت بعد علاقات تجارية أو سببية أوسع.", "يحتاج التصوير النهري واللقطات الجوية إلى تراخيص أو تصوير محلي.", "خطر أن تصبح الحلقة سياحية لا تاريخية إن لم تُدعّم محطات التأسيس بمصادر إضافية."],
        ),
        _concept(
            "episode01_concept_house_of_wisdom",
            "بيت الحكمة: حين أصبحت بغداد مدينة للمعرفة",
            "تبدأ الحلقة بسؤال عن سر اقتران بغداد بالمعرفة، ثم تنتقل من تأسيس المدينة إلى بيت الحكمة بوصفه مدخلاً إلى قصتها الفكرية.",
            "مخطوطة مضاءة ويد تقلب صفحة، ثم سؤال: كيف ارتبط اسم بغداد بذاكرة العلم؟",
            "مشاهد عربي مهتم بتاريخ العلوم والثقافة الإسلامية، من 16 إلى 45 عاماً.",
            "9–11 دقيقة",
            ["افتتاح بالمخطوطات", "بغداد 762: تأسيس المدينة", "بيت الحكمة ضمن الذاكرة التاريخية", "بغداد مركزاً للتعلم", "خاتمة: ما الذي نحتاجه لنفهم القصة كاملة؟"],
            knowledge,
            ["مخطوطات مرخصة", "إعادة بناء بيت الحكمة معلنة", "أدوات علمية", "رسوم أو خرائط معاصرة", "لقطات بغداد", "وثائق ترجمة وعلوم مرخصة"],
            60,
            40,
            ["هذا التصور يحمل أعلى خطر بحثي: بيت الحكمة ومركز التعلم مدعومان حالياً بمصدر واحد فقط.", "يلزم فصل الموثق عن الأساطير الشائعة حول بيت الحكمة وعدم توسيع الادعاءات بلا أدلة.", "الحصول على مخطوطات عالية الجودة يتطلب تحققاً دقيقاً من الملكية والرخص."],
        ),
    ]
    output = Path(paths.working_root) / "production-v4" / "episode-01-preproduction"
    payload = {
        "schema_version": CONCEPTS_SCHEMA,
        "created_at": CANONICAL_TIMESTAMP,
        "project_id": json.loads((root / "project.json").read_text(encoding="utf-8-sig"))["project_id"],
        "concepts": concepts,
        "selection": "USER_SELECTION_REQUIRED",
    }
    concepts_path = output / "episode-01-concepts.json"
    _write(concepts_path, json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", replace=replace)
    markdown = ["# Episode 01 — Preproduction Concepts", "", "Selection: USER_SELECTION_REQUIRED", ""]
    for item in concepts:
        markdown.extend([
            f"## {item['temporary_title']}", "", f"- الفكرة المركزية: {item['central_idea']}", f"- Hook: {item['hook_first_10_seconds']}", f"- الجمهور: {item['target_audience']}", f"- المدة: {item['proposed_duration']}", f"- الصور الثابتة / الحركة: {item['visual_mix_percent']['still_images']}% / {item['visual_mix_percent']['moving_footage_or_motion_design']}%", "", "### البنية", *[f"- {step}" for step in item["story_structure"]], "", "### المخاطر", *[f"- {risk}" for risk in item["research_and_production_risks"]], "",
        ])
    markdown_path = output / "episode-01-concepts.md"
    _write(markdown_path, "\n".join(markdown) + "\n", replace=replace)
    report = {
        "schema_version": REPORT_SCHEMA,
        "created_at": CANONICAL_TIMESTAMP,
        "status": "AWAITING_USER_CONCEPT_SELECTION",
        "concept_count": len(concepts),
        "input_counts": {"claims": len(claims), "sources": len(sources_payload.get("sources", [])), "research_gaps": len(gaps_payload.get("gaps", [])), "research_tasks": len(tasks_payload.get("tasks", []))},
        "evidence_limitations": "All six currently available Baghdad claims have single-source research gaps and require independent corroboration before final production scripting.",
        "prohibited_actions_not_performed": ["Azure TTS", "image generation", "video rendering", "final asset acquisition"],
        "concepts_sha256": sha256(concepts_path.read_bytes()).hexdigest(),
    }
    report_path = output / "episode-01-preproduction-report.json"
    _write(report_path, json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", replace=replace)
    return {"concepts": str(concepts_path.relative_to(root).as_posix()), "markdown": str(markdown_path.relative_to(root).as_posix()), "report": str(report_path.relative_to(root).as_posix()), "status": report["status"]}
