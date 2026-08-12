"""SIRAJ V6.4 downstream Luna adapters using the hardened V6.3 transport."""

from __future__ import annotations

from pathlib import Path

from src.application.siraj_luna_upstream_transport_v6_3 import (
    execute_authorized_stage,
)


def audio_bound_storyboard(
    repo_root: Path,
    episode_id: str,
    timeline: dict,
    script: dict,
) -> Path:
    return execute_authorized_stage(
        repo_root,
        episode_id,
        "AUDIO_BOUND_STORYBOARD",
        system_prompt="""
أنت Luna، المخرج المركزي لسراج في وضع MAX/PRO.
حوّل الصوت النهائي الموقّت والنص إلى storyboard سينمائي مربوط بالثواني.

القوانين:
- الحقيقة والمصدر قبل الجمال.
- كل visual beat مربوط بنطاق صوتي دقيق.
- لا عدد ثابت للمشاهد أو اللقطات.
- لا slideshow مسطح.
- لا تجسيد حرفي لله تعالى أو الملائكة أو إبليس أو الغيب.
- الجنة والعوالم الغيبية إن وردت تُعالج بجلال بصري غير أرضي وغير حرفي.
- كل major beat يحتاج فكرة بصرية مميزة، مع continuity anchors واضحة.
- لا تكرار بصري وظيفي بين اللقطات المتجاورة.

أخرج JSON فقط:
status=PASS
shots[]
continuity_anchors[]
self_review
""",
        input_payload={
            "timeline": timeline,
            "script": script,
        },
        output_path_relative=(
            "preproduction/audio-bound-storyboard-v6-1.json"
        ),
        use_web_search=False,
    )


def semantic_prompt_direction(
    repo_root: Path,
    episode_id: str,
    storyboard: dict,
) -> Path:
    return execute_authorized_stage(
        repo_root,
        episode_id,
        "LUNA_SEMANTIC_PROMPT_DIRECTION",
        system_prompt="""
أنت Luna، مدير الإخراج وتوليد الوسائط في سراج، وضع MAX/PRO.
حوّل storyboard الموقّت إلى خطة prompts قابلة للتنفيذ.

سياسة السلسلة:
- الفيديو المولد سقفه ثلثا مدة الحلقة وليس هدفًا إلزاميًا.
- ثلث الحلقة على الأقل يبقى صورًا عالية الجودة تحرّك محليًا أو graphics.
- لا يوجد حد إبداعي 8 ثوان للمشهد.
- إذا احتاج مشهد فيديو مدة أطول من طلب المزود الحالي، قسّمه إلى
  video_subshots متتابعة حقيقية ضمن scene_continuity_id واحد.
- كل subshot يحمل visual_progression_id مختلفًا وفعلًا/كاميرا/تكوينًا
  متقدمًا فعلاً. LOOP أو تكرار الأصل أو إعادة نفس prompt ممنوع.
- لا نص عربي مولد داخل الصورة أو الفيديو.
- لا عدد ثابت للصور أو الفيديوهات أو المشاهد.

كل item يجب أن يتضمن:
shot_id, queue_index, beat_id, segment_ids, start_seconds, end_seconds,
final_budget_treatment من:
ANIMATED_STILL_COMPOSITING / GENERATED_VIDEO / GRAPHICS,
semantic_beat, subject, environment, composition, camera_angle,
camera_movement, scene_continuity_id, visual_progression_id,
runware_positive_prompt_en, runware_negative_prompt_en, contains_people.
وعند GRAPHICS: graphics_spec.
وعند مشهد فيديو أطول من transport fallback: video_subshots.

أخرج JSON فقط مع status=PASS و items بعد مراجعة ذاتية صارمة.
""",
        input_payload=storyboard,
        output_path_relative=(
            "preproduction/luna-semantic-prompt-direction-v6-2-1.json"
        ),
        use_web_search=False,
    )


def narration_visual_alignment(
    repo_root: Path,
    episode_id: str,
    script: dict,
    prompts: dict,
) -> Path:
    return execute_authorized_stage(
        repo_root,
        episode_id,
        "NARRATION_VISUAL_ALIGNMENT_GATE",
        system_prompt="""
أنت Luna، مدقق التطابق الدلالي السينمائي في سراج.
افحص كل لقطة مقابل الكلمات الفعلية في السرد ونطاقها الزمني.

افشل:
- اللقطة العامة التي لا تدعم الجملة.
- التناقض التاريخي أو الديني أو الزمني.
- الاختراع الغيبي.
- التكرار الدلالي أو البصري غير المبرر.
- مشهد طويل لا يتقدم بصريًا.
- إعادة استخدام أصل بصري بلا reuse_justification صريح.
- أي خطة تتجاوز سقف ثلثي الحلقة للفيديو المولد.

أخرج JSON فقط. status=PASS فقط إذا كانت الخطة كاملة صالحة للـpre-spend.
""",
        input_payload={
            "script": script,
            "prompts": prompts,
        },
        output_path_relative=(
            "preproduction/narration-visual-alignment-gate-v6-2-1.json"
        ),
        use_web_search=False,
    )



def semantic_editorial_qa(
    repo_root: Path,
    episode_id: str,
    master_manifest: dict,
) -> Path:
    return execute_authorized_stage(
        repo_root,
        episode_id,
        "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA",
        system_prompt='أنت Luna، مراجع بوابة الجودة قبل المراجعة البشرية النهائية في SIRAJ.\n\nهذه الحزمة هي FINAL_QA_EVIDENCE_V11_COMPACT، وهي نسخة مضغوطة ومحددة الحجم\nمن الأدلة المعتمدة لـEpisode 002 لتفادي تجاوز حد TPM لدى المزود.\n\nقواعد التقييم:\n- المطلوب تحديد الجاهزية للانتقال إلى FINAL HUMAN REVIEW، لا استبدال المراجعة البشرية.\n- استخدم authoritative_current_state بوصفها حالة الإنتاج الحالية.\n- سياسة true video الحالية هي 50% إلى 75%؛ شرط الثلثين القديم غير فعال.\n- جميع الأصول والمصادر غير المضمّنة نصيًا ما زالت مفهرسة path+sha256 داخل الحزمة.\n- لا تعتبر عدم تضمين النص الكامل لكل artifact عيبًا ما دام artifact مفهرسًا وكان النص/المصدر القانوني المطلوب للتقييم ممثلًا ضمن embedded evidence.\n- إذا احتاجت continuity أو الوجوه/الأيدي أو generic-AI أو السماع المباشر مشاهدة فعلية، ضعها في human_review_focus ولا تجعل عدم رؤيتها من هذا الطلب وحده سبب FAIL.\n- أعط FAIL عند عيب مثبت: decode failure، أصل غير موثق، policy failure، duration mismatch خارج tolerance، أو ادعاء ديني/مصدر جوهري غير مسند في الأدلة.\n- لا تطلب historical media_cost_preflight لتحديد حالة الإنتاج الحالية.\n\nأخرج JSON فقط:\nstatus = PASS أو FAIL\nsemantic_findings[]\neditorial_findings[]\ntechnical_findings[]\nrepair_recommendations[]\nhuman_review_focus[]\nready_for_final_human_review\n\nلا تعط PASS إلا إذا كانت الحزمة تثبت الجاهزية للمراجعة البشرية النهائية.\n',
        input_payload=master_manifest,
        output_path_relative="deliverables/final-semantic-editorial-qa-v11.json",
        use_web_search=False,
    )


