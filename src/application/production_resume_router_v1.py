from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from src.application.autonomous_episode_orchestrator_v1 import (
    load_orchestrator_state,
)

RELEASE = "SIRAJ_DESKTOP_COMPLETE_WORKSPACE_AND_RESUME_V1"


@dataclass(frozen=True, slots=True)
class ProductionResumeDirective:
    status: str
    stage: str
    target_tab: str
    action: str
    label_ar: str
    detail_ar: str
    can_run_automatically: bool = False
    requires_human: bool = False
    requires_paid_confirmation: bool = False
    ready_to_publish: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _directive(
    status: str,
    stage: str,
    target_tab: str,
    action: str,
    label_ar: str,
    detail_ar: str,
    *,
    automatic: bool = False,
    human: bool = False,
    paid: bool = False,
    ready: bool = False,
) -> ProductionResumeDirective:
    return ProductionResumeDirective(
        status=status,
        stage=stage,
        target_tab=target_tab,
        action=action,
        label_ar=label_ar,
        detail_ar=detail_ar,
        can_run_automatically=automatic,
        requires_human=human,
        requires_paid_confirmation=paid,
        ready_to_publish=ready,
    )


def resolve_resume_directive_from_state(
    state: Mapping[str, Any],
) -> ProductionResumeDirective:
    status = str(state.get("status") or "UNKNOWN").strip().upper()
    stage = str(state.get("stage") or "UNKNOWN").strip().upper()
    last_error = str(state.get("last_error") or "").strip()

    if status == "READY_TO_PUBLISH" or stage == "READY_TO_PUBLISH":
        return _directive(
            status,
            stage,
            "qa",
            "OPEN_PUBLISH_PACKAGE",
            "فتح حزمة النشر الجاهزة",
            "الفيديو وبيانات YouTube والمراجعة النهائية جاهزة. يبقى الرفع والنشر اليدويان.",
            ready=True,
        )

    if status == "AWAITING_HUMAN_FINAL_REVIEW" or stage == "HUMAN_FINAL_REVIEW":
        return _directive(
            status,
            stage,
            "qa",
            "OPEN_FINAL_REVIEW",
            "فتح المراجعة النهائية وحزمة النشر",
            "أكمل مشاهدة الحلقة وتأكيد البنود السبعة ثم أنشئ حزمة النشر.",
            human=True,
        )

    if status == "HUMAN_FINAL_REVIEW_CHANGES_REQUESTED":
        return _directive(
            status,
            stage,
            "qa",
            "RUN_QA",
            "إعادة الفحص بعد تنفيذ الإصلاح",
            "طلب المراجعة النهائية إصلاحًا. أي تغيير بصري أو صوتي أو تحريري يتطلب QA جديدًا.",
            automatic=True,
        )

    if status in {
        "FINAL_RENDER_READY_FOR_QA",
        "AUTOMATIC_QA_FAILED",
        "AUTOMATIC_QA_BLOCKED",
    } or stage == "AUTOMATIC_QA":
        return _directive(
            status,
            stage,
            "qa",
            "RUN_QA",
            "تشغيل الفحص الآلي والإصلاح الجزئي",
            "سيفحص سراج الحلقة محليًا ويعيد فقط اللقطة أو الـmux المتضرر.",
            automatic=True,
        )

    if status == "AUTOMATIC_QA_ACTIVE":
        return _directive(
            status,
            stage,
            "qa",
            "WAIT",
            "الفحص الآلي يعمل الآن",
            "اترك العملية تكمل ثم حدّث الحالة.",
        )

    if status in {"SFX_MIX_READY", "STRUCTURAL_MONTAGE_FAILED"} or stage == "STRUCTURAL_MONTAGE":
        return _directive(
            status,
            stage,
            "montage",
            "RUN_MONTAGE",
            "استكمال المونتاج وإخراج الحلقة",
            "المواد والصوت جاهزان؛ سيستأنف سراج المونتاج محليًا دون طلبات مدفوعة.",
            automatic=True,
        )

    if status in {"STRUCTURAL_MONTAGE_ACTIVE"}:
        return _directive(
            status,
            stage,
            "montage",
            "WAIT",
            "المونتاج يعمل الآن",
            "يتم تركيب الحلقة محليًا. حدّث الحالة بعد اكتماله.",
        )

    if status in {
        "MEDIA_EXECUTION_COMPLETE",
        "SFX_MIX_FAILED",
        "AUDIO_MIX_FAILED",
    } or stage == "SFX_DESIGN":
        return _directive(
            status,
            stage,
            "sfx",
            "RUN_SFX",
            "استكمال المؤثرات والمكساج الصوتي",
            "سيبني سراج الماستر الصوتي محليًا من التعليق والمؤثرات المعتمدة.",
            automatic=True,
        )

    if status in {"SFX_MIX_ACTIVE", "AUDIO_MIX_ACTIVE"}:
        return _directive(
            status,
            stage,
            "sfx",
            "WAIT",
            "المكساج الصوتي يعمل الآن",
            "اترك العملية تكمل ثم حدّث الحالة.",
        )

    media_stages = {
        "BUDGET_PREFLIGHT",
        "RUNWARE_IMAGE_GENERATION",
        "RUNWARE_VIDEO_GENERATION",
        "LOCAL_GRAPHICS_RENDER",
        "ELEVENLABS_TTS",
    }
    if (
        stage in media_stages
        or "MEDIA_QUEUE" in status
        or "MEDIA_EXECUTION" in status
        or "RUNWARE" in status
        or "ELEVENLABS" in status
    ):
        return _directive(
            status,
            stage,
            "media",
            "OPEN_MEDIA_EXECUTION",
            "استكمال تنفيذ الوسائط",
            "سيشغّل سراج الجرافيك المحلي مباشرة، بينما تبقى طلبات Runware وElevenLabs خلف تأكيد تكلفة صريح.",
            paid=True,
        )

    editorial_stages = {
        "EVIDENCE_RESEARCH",
        "SCRIPT_WRITING",
        "STORYBOARD_AND_MEDIA_PLANNING",
    }
    if (
        status in {
            "SCOPE_APPROVED_AUTOMATIC_PIPELINE_QUEUED",
            "EDITORIAL_PIPELINE_FAILED",
        }
        or stage in editorial_stages
        or "EDITORIAL" in status
    ):
        return _directive(
            status,
            stage,
            "orchestrator",
            "RUN_EDITORIAL",
            "استئناف البحث والنص والستوريبورد",
            "سيستأنف Luna من آخر إيصال صحيح، ثم يبني مواصفات الجرافيك وطابور الوسائط.",
            automatic=True,
        )

    if status in {"GENERATING_SCOPE_WITH_LUNA"}:
        return _directive(
            status,
            stage,
            "orchestrator",
            "WAIT",
            "Luna يبني مقترح الحلقة الآن",
            "انتظر اكتمال المقترح ثم راجعه واعتمده.",
        )

    if status == "AWAITING_HUMAN_SCOPE_REVIEW" or stage == "HUMAN_SCOPE_REVIEW":
        return _directive(
            status,
            stage,
            "orchestrator",
            "REVIEW_SCOPE",
            "مراجعة واعتماد موضوع الحلقة وأحداثها",
            "هذه هي البوابة البشرية الأولى؛ عدّل المقترح أو اعتمده لبدء السلسلة التحريرية.",
            human=True,
        )

    if status in {
        "IDLE_READY_FOR_NEXT_EPISODE",
        "SCOPE_PROVIDER_ERROR",
        "UNKNOWN",
    } or stage == "TOPIC_AND_EVENT_PROPOSAL":
        detail = "ابدأ باختيار موضوع الحلقة وأحداثها عبر Luna."
        if last_error:
            detail += " آخر خطأ: " + last_error
        return _directive(
            status,
            stage,
            "orchestrator",
            "GENERATE_SCOPE",
            "إنتاج الحلقة التالية",
            detail,
            automatic=True,
        )

    if last_error:
        return _directive(
            status,
            stage,
            "orchestrator",
            "INSPECT_BLOCKER",
            "فحص سبب توقف الإنتاج",
            last_error,
        )

    return _directive(
        status,
        stage,
        "orchestrator",
        "REFRESH",
        "تحديث حالة الإنتاج",
        "لم يتعرف الموجّه على حالة تنفيذية محددة؛ حدّث البيانات وافتح سجل المرحلة الحالية.",
    )


def resolve_resume_directive(repo_root: Path) -> ProductionResumeDirective:
    return resolve_resume_directive_from_state(
        load_orchestrator_state(repo_root.resolve())
    )
