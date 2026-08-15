# SIRAJ OS
## Master Development Roadmap

آخر تحديث:
2026-08-12

========================================================
SIRAJ SHORTS LEGACY TIMING RESOLVER V1 - 2026-08-14
========================================================

Status:
LEGACY_TIMING_RESOLVER_READY_AND_EP001_SHORTS_SOURCE_ADMISSION_PASS

Certification:
- Generic offline resolver v1.0.4 added for canonical, native, absolute TTS/timeline-repair, sentence/segment, and explicit user-selected timing authorities.
- EP001 timing was AUTO_DISCOVERED from the trusted absolute TTS/timeline-repair artifact and then CACHE_REUSED by the hash-bound canonical transcript.
- EP001 Source Discovery: READY; ready_without_manual_file=true; manual transcript selection is not required.
- EP001 Source Admission: PASS; 43 segments; FINAL_VIDEO_ABSOLUTE; first timestamp 0.6; last timestamp 1312.24483; duration 1320.0 seconds.
- EP001 local Shorts analysis: startable; 229 candidates discovered; no render/export/montage/publication.
- Equal-priority ambiguity, stale hashes, missing evidence, unsupported timebase, and upstream changes fail closed.
- Full direct suite: 789 passed, 1 historical skip, 9 release-packaging errors from an existing ignored build/dist-info collision; release packaging itself passed 9/9 after reversible build isolation and restoration.
- Resolver/Shorts/Desktop/PR01/constitutional matrix: 428 passed; additional Shorts integration: 12 passed.

Safety:
- Provider calls: 0.
- Paid calls: 0.
- Network production calls: 0.
- New TTS/narration/visual generation: 0/0/0.
- Production render/montage/publication: 0/0/0.
- Retries/resubmissions: 0/0.
- Unified constitution and core enforcement were not modified.
- Historical untracked evidence was preserved and not staged.

Evidence:
- reports/shorts-legacy-timing-resolver-v1/SHORTS_LEGACY_TIMING_GAP_AUDIT_V1.json
- reports/shorts-legacy-timing-resolver-v1/EP001_LEGACY_TIMING_RECOVERY_EVIDENCE_V1.json
- reports/shorts-legacy-timing-resolver-v1/SIRAJ_SHORTS_LEGACY_TIMING_RESOLVER_CERTIFICATION_V1.json
- reports/shorts-legacy-timing-resolver-v1/SIRAJ_SHORTS_LEGACY_TIMING_RESOLVER_FINAL_REPORT_V1.md

NEXT=OPEN_SIRAJ -> SHORTS -> SELECT EPISODE 1 -> ANALYZE

========================================================
SIRAJ PR01 PRODUCTION READINESS BINDING - 2026-08-14
========================================================

Status:
PR01_PRODUCTION_READINESS_PASS

Certification:
- Production readiness: READY_FOR_EPISODE_SPECIFIC_PREFLIGHT.
- Production authorization: FALSE.
- Paid execution authorization: FALSE.
- Publication authorization: FALSE.
- Critical/high unresolved: 0.
- M01 audio delivery: PASS with actual synthetic bytes measured by FFmpeg loudnorm and duration preservation check.
- M02 provider binding: PASS for exact RUNWARE / google:veo@3.1-lite, Decimal pricing, exact payload, and hash-bound Desktop gate.
- M03 face screening: PASS with local YuNet model hash, threshold sweep, 100% critical-positive recall, and helper-only status.
- EP002 R27: exact 27-unit inventory handoff only; 0 human review decisions; montage and QA false.
- Full configured suite: 774 passed, 1 pre-existing external_ai opt-in skip, 0 failed, 0 errors.
- Git staged diff check: PASS.

Safety:
- Provider calls: 0.
- Paid calls: 0.
- Network production calls: 0.
- Retries/resubmissions: 0.
- Montage/publication: 0/0.
- UNKNOWN attempt remains blocked with no retry or resubmission.
- Unified constitution bundle was not modified.

Evidence:
- reports/pr01-production-readiness/SIRAJ_PR01_PRODUCTION_READINESS_CERTIFICATION_V1.json
- reports/pr01-production-readiness/PR01_FINAL_REPORT_V1.md
- reports/pr01-production-readiness/SIRAJ_PRODUCTION_READINESS_PROFILE_V1.json
- reports/pr01-production-readiness/PR01_CONFLICT_MATRIX_V1.json
- reports/pr01-production-readiness/PR01_GAP_ENFORCEMENT_MATRIX_V1.json
- reports/pr01-production-readiness/PR01_DEPENDENCY_APPROVAL_INVALIDATION_MODEL_V1.json
- reports/pr01-production-readiness/EP002_R27_REVIEW_INPUT_MANIFEST_V1.json

NEXT=EP002_R27_RENDER_RECERTIFICATION

========================================================

========================================================
SIRAJ SHORTS DESKTOP UX ENVIRONMENT RECOVERY AND FINAL CERTIFICATION - 2026-08-14
========================================================

Status:
SHORTS_DESKTOP_UX_READY_FOR_PRODUCTION_USE

Certification:
- Canonical Desktop environment: historical-fixture-venv-20260716, Python 3.13.14.
- Full repository suite: 764 passed, 1 external_ai deselected, 0 failed, 0 errors, 0 skipped.
- Shorts/Desktop matrix: 68 passed, 0 failed, 0 errors, 0 skipped.
- Qt geometry matrix: 20/20 passed across 1280x720, 1366x768, 1600x900, 1920x1080, 2560x1440 and 100/125/150/200% scale factors.
- Windows visual review: 18/18 representative states passed.
- Native episode picker: ExistingFile, AcceptOpen, ordered video filters, native interaction fixture PASS.
- Full offline/local Desktop E2E: source admission, analysis, candidate selection, portfolio, local render, QA, human review, and local export PASS.
- Critical unresolved gaps: 0.
- High unresolved gaps: 0.
- Medium unresolved gaps: 0.
- Python compileall, pip check, secret scan, and staged diff check: PASS.
- Ruff/typecheck: NOT_CONFIGURED.

Safety:
- Provider calls: 0.
- Paid calls: 0.
- Network production calls: 0.
- YouTube/publication calls: 0/0.
- Retries/resubmissions: 0/0.
- Montage/new TTS/new visual generation: 0/0/0.
- Human final episode certification, public title, and thumbnail remain human-owned.
- Paid execution remains explicit Desktop click only.
- Unified constitution and core enforcement were not modified.

Evidence:
- reports/shorts-derivative-engine-v1/SHORTS_DESKTOP_UX_FINAL_CERTIFICATION_V1.json
- reports/shorts-derivative-engine-v1/SHORTS_DESKTOP_UX_FINAL_REPORT_V1.md
- reports/shorts-derivative-engine-v1/SHORTS_DESKTOP_UX_GEOMETRY_MATRIX_V1.json
- reports/shorts-derivative-engine-v1/SHORTS_DESKTOP_UX_FILE_PICKER_CERTIFICATION_V1.json
- reports/shorts-derivative-engine-v1/SHORTS_DESKTOP_UX_E2E_CERTIFICATION_V1.json
- reports/shorts-derivative-engine-v1/SHORTS_UX_VISUAL_REVIEW_V1.json

NEXT=HUMAN_SELECTS_AN_ADMITTED_EPISODE_FOR_A_CONTROLLED_LOCAL_SHORTS_RUN
VISION
========================================================

Siraj هو نظام إنتاج أفلام وثائقية يعمل بالذكاء الاصطناعي.

الهدف النهائي:

Source
↓
Knowledge Extraction
↓
Knowledge Graph
↓
Research
↓
Outline
↓
Narrative
↓
Script
↓
Director
↓
Scene Planning
↓
Image Prompt Generation
↓
Voice
↓
Video
↓
Final Documentary

========================================================
CURRENT PROJECT STATUS
========================================================

[✓] Architecture
[✓] Workflow
[✓] Pipeline
[✓] Knowledge Extraction V1
[✓] Knowledge Graph V1
[✓] Outline Generator
[✓] Narrative Generator
[✓] Script Generator
[✓] Scene Planner V1
[✓] Scene Generator V1
[✓] Image Prompt Generator V1

Current Phase:

KNOWLEDGE EXTRACTION V2
--------------------------------------------------------

Current Completion

Architecture ............. 100%
Pipeline ................. 100%
Extraction ............... 90%
Knowledge Graph .......... 85%
Narrative ............... 80%
Scene Planning .......... 60%
Prompt Generation ....... 70%
Director ................ 0%
Voice ................... 0%
Video ................... 0%

========================================================
DEVELOPMENT PHILOSOPHY
========================================================

1- لا يتم إضافة Features جديدة قبل استقرار المرحلة الحالية.

2- كل طبقة مسؤولة عن وظيفة واحدة فقط.

3- لا يوجد منطق مكرر.

4- لا توجد حلول مؤقتة (Hack).

5- كل تطوير يجب أن يكون قابلاً للاختبار.

6- Knowledge Graph هو المصدر الوحيد للحقيقة.

7- أي قرار معماري يجب توثيقه هنا.

========================================================
ROADMAP
========================================================

PHASE 1
STABILIZATION

Status:
COMPLETED

Goal:

توحيد المشروع وإزالة جميع الأخطاء.

Reason:

بناء قاعدة مستقرة قبل تطوير النظام.

--------------------------------------------------------

PHASE 2
KNOWLEDGE EXTRACTION V2

Status:
NEXT

Goal

تحسين استخراج المعرفة.

يشمل:

- استخراج كيانات أكثر
- استخراج الأحداث
- استخراج المواقع
- استخراج المصادر
- استخراج العلاقات
- استخراج الأسباب والنتائج
- زيادة جودة الـ JSON

Reason

كل شيء في Siraj يعتمد على جودة المعرفة.

--------------------------------------------------------

PHASE 3
KNOWLEDGE GRAPH V2

Status:
WAITING

Goal

تحويل الـ Graph إلى Graph غني.

يشمل:

- أنواع Nodes أكثر
- علاقات أكثر
- Inference
- Context Links

Reason

كل المراحل التالية تعتمد عليه.

--------------------------------------------------------

PHASE 4
DOCUMENTARY PLANNER

Status:
WAITING

Goal

استبدال التخطيط البسيط بتخطيط وثائقي احترافي.

Reason

الفيلم لا يُبنى من شخصيات وأحداث فقط.

--------------------------------------------------------

PHASE 5
NARRATIVE ENGINE V2

Status:
WAITING

Goal

إنتاج سرد مترابط بدون تكرار.

--------------------------------------------------------

PHASE 6
DOCUMENTARY DIRECTOR

Status:
WAITING

Goal

إضافة:

- Camera
- Shots
- Timing
- Transitions
- Cinematic Language

--------------------------------------------------------

PHASE 7
IMAGE PROMPT ENGINE V2

Status:
WAITING

Goal

تحويل المشاهد إلى Prompts احترافية.

--------------------------------------------------------

PHASE 8
VOICE ENGINE

Status:
WAITING

--------------------------------------------------------

PHASE 9
VIDEO ENGINE

Status:
WAITING

--------------------------------------------------------

PHASE 10
FINAL RENDER PIPELINE

Status:
WAITING

========================================================
CURRENT ISSUES
========================================================

[ ] Knowledge Extraction ما زال بسيطاً.

[ ] Scene Planner يعتمد على Template.

[ ] Narrative يحتوي على بعض التكرار.

[ ] Image Prompts تصف النص أكثر من المشهد.

[ ] Fact Verification لا يستخدم مصادر حقيقية.

[ ] Source Extraction يحتاج إعادة تصميم.

[ ] يجب إضافة سياسة تمنع تمثيل الأنبياء بصرياً.

========================================================
ENGINEERING DECISIONS
========================================================

2026-07-08

- اعتماد Knowledge Graph كمصدر الحقيقة الوحيد.

- عدم إضافة أي Feature قبل انتهاء الاستقرار.

- اعتماد PROJECT_PROGRESS.md كمرجع رسمي للمشروع.

========================================================
SESSION LOG
========================================================

Session #1

تم:

- إصلاح Pipeline
- إصلاح Parser
- إصلاح Model Factory
- إصلاح Workflow
- تشغيل النظام حتى إنتاج المشاهد

المرحلة التالية:

Knowledge Extraction V2

========================================================
RULES
========================================================

قبل كل جلسة:

1- مراجعة هذا الملف.

بعد كل جلسة:

1- تحديث ما تم.
2- تحديث المرحلة الحالية.
3- تحديث المشاكل.
4- تحديث القرارات.
5- تحديد أول خطوة للجلسة القادمة.

لا يتم تجاوز أي مرحلة قبل إنهائها بالكامل.



Session #2

تم:

✓ إنشاء منظومة Architecture Analysis كاملة.

✓ إنشاء Scanner للمشروع.

✓ إنشاء Symbol Analyzer.

✓ إنشاء Dependency Graph.

✓ إنشاء Reverse Dependency Graph.

✓ إنشاء Reachability Engine.

✓ إنشاء Architecture Intelligence Engine.

✓ إنشاء Duplicate Detector.

✓ إنشاء Execution Graph.

✓ إنشاء Call Chain Analyzer.

✓ إنشاء Module Clusterizer.

✓ إنشاء Refactor Engine (Safe Mode).

✓ إنشاء Final Architecture Report.

✓ بناء قاعدة بيانات كاملة عن المشروع.

✓ إنشاء PROJECT INVENTORY.

✓ تنفيذ Identity Audit.

النتيجة:

أصبح المشروع قابلاً للتحليل الكامل قبل أي إعادة هيكلة.

جميع محركات التحليل أصبحت تعمل.

لا تم إجراء أي حذف فعلي للحفاظ على استقرار النظام.

المرحلة القادمة:

Knowledge Extraction V2



2026-07-08

تم اعتماد Architecture Intelligence كطبقة دائمة داخل المشروع.

أي عملية حذف أو دمج مستقبلية يجب أن تمر عبر:

Backup
↓

Validation
↓

Dry Run
↓

Execution

Session #3

تم:

✓ إعادة بناء Knowledge Extraction Architecture.

✓ تحويل جميع الـ Extractors إلى Candidate-based Architecture.

✓ إنشاء Candidate Models كطبقة وسيطة موحدة بين الاستخراج والـ Domain Objects.

✓ إنشاء Confidence Engine لحساب درجة الثقة لكل عنصر مستخرج.

✓ إنشاء Quality Engine لتنقية النتائج وإزالة العناصر منخفضة الجودة.

✓ إعادة تصميم Object Mapper وتحويل النتائج إلى Domain Knowledge Objects.

✓ إضافة Entity Resolution لإزالة التكرار وتوحيد الأسماء والـ Aliases.

✓ إضافة Knowledge Quality Engine.

✓ إضافة Knowledge Score لكل كائن معرفي.

✓ إضافة تصنيف جودة (HIGH / MEDIUM / LOW).

✓ توحيد Metadata بين جميع Domain Objects.

✓ تحويل العلاقات إلى علاقات دلالية (Semantic Relationships) بدلاً من الاعتماد على النص الخام.

✓ إعادة بناء Pipeline بالكامل ليدعم:

Document
↓
Candidate Extraction
↓
Confidence Evaluation
↓
Quality Filtering
↓
Domain Object Mapping
↓
Entity Resolution
↓
Knowledge Quality Evaluation

النتيجة:

أصبحت طبقة استخراج المعرفة تعمل كنظام متعدد المراحل (Multi-stage Knowledge Extraction Pipeline) بدلاً من مجموعة Extractors مستقلة.

كل عنصر معرفي أصبح يحتوي على Metadata موحدة تشمل:

* extractor
* source
* confidence
* knowledge_score
* quality

كما أصبح النظام جاهزاً للانتقال إلى Knowledge Graph V2 دون الحاجة لإعادة تصميم طبقة الاستخراج.

المرحلة القادمة:

استكمال Knowledge Extraction V2 عبر:

* Source Intelligence
* Evidence Linking
* Conflict Detection
* Canonical Entity Resolution
* Knowledge Graph Builder V2

قرارات هندسية جديدة:

* اعتماد Candidate Objects كصيغة تبادل داخلية بين جميع محركات الاستخراج.

* منع انتقال أي عنصر إلى Domain Objects قبل المرور عبر Quality Engine.

* اعتبار Knowledge Score المؤشر الرسمي لجودة أي معلومة داخل النظام.

* فصل طبقة الاستخراج بالكامل عن طبقة بناء الرسم البياني المعرفي لتسهيل التطوير والاختبار.






إذا قسمنا المشروع إلى طبقات كبيرة، فسيكون كالتالي:

المرحلة 0 — البنية الأساسية (اكتملت)

تم إنجاز:

هيكل المشروع
Domain Models
طبقات التطبيق
Infrastructure
نظام الـ Pipelines
Configuration
Dependency Injection الأساسي

الحالة:
100%

المرحلة 1 — Document Processing (اكتملت)

تم إنجاز:

Document Parser
تقسيم الوثيقة
Paragraphs
Sentences
Context Builder
SourceReference

أصبح النظام يعرف:

من أين جاءت كل معلومة.

الحالة:
100%

المرحلة 2 — Knowledge Extraction (نحن هنا)

أنجزنا تقريبًا بالكامل:

Extractors

✅ Entity Extractor

✅ Event Extractor

✅ Claim Extractor

✅ Relationship Extractor

✅ Location Extractor

✅ Source Extractor

✅ Evidence Extractor

Candidate Models

اكتملت.

Object Mapper

اكتمل.

Object Merger

اكتمل.

Quality Engine

نسخة أولية.

Extraction Pipeline

اكتمل.

حالياً أصبح بإمكاننا استخراج:

أشخاص
أماكن
أحداث
ادعاءات
علاقات

وتحويلها إلى Domain Objects.

ما ينقص داخل المرحلة الثانية

وهذا هو الجزء الكبير.

1)

Entity Resolution

ليس مجرد إزالة التكرار.

بل معرفة أن:

Muhammad

Prophet Muhammad

Muhammad ﷺ

رسول الله

النبي محمد

كلها شخص واحد.

2)

Knowledge Graph Builder

تحويل العلاقات إلى Graph.

مثلاً:

Muhammad

↓

commanded

↓

Muslim Army

↓

fought

↓

Quraysh

↓

at

↓

Badr

3)

Knowledge Storage

حفظ الرسم البياني.

قد يكون:

SQLite

Neo4j

Postgres

أي قاعدة.

4)

Evidence Linking

كل Claim يجب أن يعرف:

مصدره
الفقرة
الجملة
الفيديو
التوقيت
5)

Confidence Engine

دمج درجات الثقة.

6)

Conflict Detection

إذا وجد:

624 CE

وفي مصدر آخر:

625 CE

يعرف أنه يوجد تعارض.

7)

Deduplication المتقدم

حالياً يعتمد على الاسم.

لكن لاحقاً يعتمد على:

Semantic Similarity.

بعد انتهاء هذه المرحلة يصبح لدينا:

Knowledge Graph كامل.

المرحلة 3 — AI Reasoning Layer

هذه مرحلة ضخمة.

يبنى فوق الـ Graph.

فيها:

Summarization
Timeline Builder
Question Answering
Fact Checking
Contradiction Detection
Story Generator
Scene Planner
Script Planner

هذه المرحلة هي التي تحول البيانات إلى "فهم".

المرحلة 4 — Content Planning

هنا يبدأ المشروع يشبه ما تتخيله.

النظام يصبح قادراً على إنتاج:

فكرة فيديو
Hook
Opening
Sections
Ending
CTA

بدون تدخل.

المرحلة 5 — Script Generator

ينتج:

Script طويل
Short
Reel
TikTok
Podcast
Documentary
Educational Video
المرحلة 6 — Visual Planner

هذه أهم مرحلة بالنسبة للمخرجات المرئية.

هنا يبني:

Scene 1

Scene 2

Scene 3

...

لكل مشهد:

الشخصيات
المكان
الإضاءة
زاوية الكاميرا
الحركة
المشاعر
الألوان
الملابس

أي يصبح لدينا Storyboard كامل.

المرحلة 7 — Asset Generator

هنا يبدأ إنتاج:

صور

Characters

Backgrounds

Maps

Infographics

Icons

B-roll

Motion Graphics

الخ.

المرحلة 8 — Voice Layer

إنشاء:

التعليق الصوتي
الأصوات
المؤثرات
الموسيقى
المرحلة 9 — Video Composer

يجمع كل شيء.

وينتج:

MP4

Vertical

Horizontal

Square

أي نسبة تريدها.

المرحلة 10 — Multi Platform Export

يصدر:

YouTube

Shorts

Instagram

Reels

TikTok

Facebook

X

LinkedIn

Podcast

متى سنرى أول مخرجات؟

ليس بعد المرحلة العاشرة.

بل قبلها بكثير.

أول نقطة يمكن رؤية مخرجات حقيقية هي بعد اكتمال:

المرحلة الثانية (Knowledge Graph)
جزء أساسي من المرحلة الثالثة (Reasoning)
المرحلة الرابعة (Content Planning)
بداية المرحلة الخامسة (Script Generation)

عندها سنكون قادرين على إدخال موضوع مثل:

"غزوة بدر"

والنظام سيولد تلقائيًا:

ملخصًا دقيقًا.
مخطط الفيديو.
السكربت.
ترتيب المشاهد.
قائمة الشخصيات.
قائمة المواقع.
التسلسل الزمني.
الاقتباسات والأدلة.

بعد إضافة Visual Planner (المرحلة السادسة)، سيصبح قادرًا أيضًا على توليد أوامر الصور لكل مشهد (Prompts) وربطها بالسكربت.

أما الفيديو الكامل الآلي (صور/فيديو + تعليق صوتي + مونتاج + تصدير)، فهذا يتطلب اكتمال المراحل السابعة إلى التاسعة.

تقديري للتقدم الحالي

بناءً على ما أنجزناه، المشروع الكلي يقف تقريبًا عند:

من حيث البنية الأساسية: نحو 35–40%.
من حيث القدرة على إنتاج فيديو جاهز للنشر: نحو 20–25%.

السبب أن الطبقات المتبقية (الاستدلال، التخطيط، التوليد البصري، التركيب) هي الأكثر تعقيدًا، لكنها تعتمد على الأساس الذي نبنيه الآن. بمجرد اكتمال طبقة المعرفة، يصبح التطوير أسرع لأن جميع المخرجات اللاحقة تعتمد على نفس الرسم البياني المعرفي بدل إعادة تحليل المحتوى في كل مرة.


الشيء الوحيد الذي أضعه كـ TODO مستقبلي:

1. تحسين EntityResolver

لأن:

Prophet Muhammad

و:

Muhammad

تم دمجهما فقط بسبب إزالة العناوين.

هذا جيد، لكن لاحقًا نحتاج Alias Registry:

مثلاً:

Muhammad:
    aliases:
        - prophet muhammad
        - muhammad ibn abdullah
        - the prophet

لكن ليس الآن.

2. إضافة اختبار رسمي للدمج

بدل الأمر اليدوي:

same_relationship = False

نضيف لاحقًا:

assert MergeRules.same_relationship(r1,r2)==True

داخل tests.

3. لا نغير GraphBuilder الآن

هذا الجزء:

graph.add_edge(
    Canonicalizer.normalize_text(rel.subject),
    Canonicalizer.normalize_text(rel.predicate),
    Canonicalizer.normalize_text(rel.object),
)

صحيح للمرحلة الحالية.


ترتيب المراحل الذي أوصي به حاليا:

✅ Extraction

✅ Object Mapping

✅ Merge

✅ Canonicalization

✅ GraphBuilder

━━━━━━━━━━━━━━━━━━━━━━

⬜ GraphIndex

⬜ GraphQueryEngine

⬜ Reasoning Engine

⬜ Memory Engine

⬜ Retrieval Engine

⬜ Ranking Engine

⬜ Knowledge Fusion

⬜ Temporal Knowledge

⬜ Contradiction Engine

⬜ Confidence Propagation





Visual Asset Architecture

Source Selection

Shot Planning

Image Generation

Narration Generation

Video Assembly

Quality Evaluation

Automatic Refinement

Publishing Pipeline

========================================================
ADAM SOURCE REVIEW DOCKET V1 — 2026-07-28
========================================================

تم:

✓ جلب 22/22 مصدراً قرآنياً وحديثياً مرشحاً.
✓ أرشفة 24 استجابة خام والتحقق من بصماتها.
✓ استخراج النص العربي آلياً من جميع المصادر الـ22.
✓ تجهيز 17 مصدراً للمقارنة البشرية المباشرة.
✓ حصر 5 مصادر تحتاج معالجة نصية موجهة.
✓ إنشاء طبقة تحسين حتمية للمطابقات الجزئية.
✓ إنشاء سجل قرار بشري موحد يغطي جميع المصادر الـ22.
✓ إنشاء بطاقات مراجعة مصدرية وربطها بالأحداث الـ14 والروابط الـ28.
✓ إنشاء حزمة NotebookLM محددة فقط للمصادر التي تبقى غير محسومة.

حالة الحوكمة:

- HUMAN_COMPARISON_COMPLETE = NO
- SOURCE_VERIFICATION_COMPLETE = NO
- AUTOMATIC_HADITH_GRADING = FORBIDDEN
- AUTOMATIC_SOURCE_AUTHENTICATION = FORBIDDEN
- AUTOMATIC_ORIGIN_CLASSIFICATION = FORBIDDEN
- HUMAN_APPROVAL = PENDING
- CURRENT_EVIDENCE_GATE = WITHHELD
- RUNWARE_LIVE_EXECUTION = BLOCKED

القيمة للمستخدم:

تقليل المراجعة من بحث مفتوح إلى قرارات محددة لكل مصدر مع نص مقترح،
موضع، فروقات، سياق مطلوب، وخيارات قرار صريحة.

القيمة المعمارية:

فصل المقارنة النصية عن تصحيح الحديث وتصنيف الأصل واعتماد السرد وفتح
بوابة الأدلة، مع نماذج مستقلة وقابلة للاختبار.

الاستخدام القريب:

استكمال المقارنة البشرية للمصادر الـ22، ثم بناء سجل تحقق مصدري معتمد
يُستخدم لاحقاً في adjudication جميع أحداث حلقة آدم.

الخطوة التالية:

تسجيل قرارات المقارنة البشرية، ثم تنفيذ مراجعة مستقلة للتصحيح
والتصنيف قبل إنشاء حزمة الأدلة المعتمدة.

========================================================
ADAM SOURCE REVIEW WORKBENCH V1 — 2026-07-28
========================================================

تم:

✓ إنهاء المعالجة النصية لجميع المصادر الـ22.
✓ إنشاء منضدة HTML محلية مستقلة للمراجعة البشرية.
✓ تضمين الروابط الخارجية والأرشيفات المحلية والنصوص المقترحة والفروقات.
✓ إضافة حفظ محلي للمسودات واستيراد/تصدير JSON.
✓ منع أي قرار افتراضي أو اختيار تلقائي.
✓ إضافة تحقق مستقل في Python لملف القرار البشري المصدر.
✓ قفل تصحيح الحديث والتوثيق وتصنيف الأصل وربط الحدث خارج هذه المرحلة.

الحالة:

- SOURCE_COUNT = 22
- ORIGINAL_READY_SOURCES = 17
- REFINED_READY_SOURCES = 5
- REMAINING_RESOLUTION_SOURCES = 0
- HUMAN_DECISIONS_RECORDED = 0
- HUMAN_COMPARISON_COMPLETE = NO
- SOURCE_VERIFICATION_COMPLETE = NO
- HUMAN_APPROVAL = PENDING
- CURRENT_EVIDENCE_GATE = WITHHELD
- RUNWARE_LIVE_EXECUTION = BLOCKED

الخطوة التالية:

تنفيذ المراجعة البشرية للمصادر الـ22، تصدير ملف القرار النهائي،
ثم التحقق منه ونشره دون فتح بوابة الأدلة.

========================================================
ADAM DELEGATED SOURCE REVIEW INGESTION V1 — 2026-07-28
========================================================

تم:

✓ إدخال الاعتماد البشري لمقارنة النصوص والمواضع للمصادر الـ22.
✓ تثبيت سياسة التفويض: الأدلة الروتينية للقرار المدعوم بالذكاء الاصطناعي،
  والمسائل المعقدة أو بالغة الأهمية للتصعيد البشري.
✓ اعتماد اكتمال التحقق من النص والموضع للمصادر الـ22.
✓ إنشاء مرشح ربط روتيني للمصادر القرآنية الـ11.
✓ إنشاء طابور بحث وتصعيد للمصادر الحديثية الـ11.
✓ تخصيص 3 مصادر بالغة الأهمية للمراجعة البشرية الصريحة.
✓ تفويض بحث 8 مصادر حديثية روتينية للذكاء الاصطناعي.
✓ إبقاء المصادقة وتصنيف الأصل وربط الأحداث غير مكتملة.
✓ إبقاء بوابة الأدلة محجوبة وتشغيل المزود ممنوعاً.

الحالة:

- HUMAN_SOURCE_REVIEW_APPROVED = YES
- SOURCE_TEXT_LOCATOR_VERIFICATION_COMPLETE = YES
- QURAN_SOURCE_COUNT = 11
- HADITH_SOURCE_COUNT = 11
- USER_ESCALATION_SOURCE_COUNT = 3
- AI_DELEGATED_SOURCE_COUNT = 8
- SOURCE_AUTHENTICATION_COMPLETE = NO
- EVENT_BINDING_COMPLETE = NO
- FULL_EPISODE_ADJUDICATION_COMPLETE = NO
- CURRENT_EVIDENCE_GATE = WITHHELD
- RUNWARE_LIVE_EXECUTION = BLOCKED

الخطوة التالية:

تنفيذ البحث الحديثي المفوض للمصادر الثمانية، ثم إعداد حزمة مراجعة مركزة
للمصادر الثلاثة بالغة الأهمية دون إعادة المستخدم إلى مراجعة الأدلة الروتينية.



========================================================
ADAM INGESTION JSON LINE-ENDING HASH FIX V1 — 2026-07-28
========================================================

تم إصلاح فشل إعادة إنشاء التقرير المحلي بعد نجاح النشر:

- السبب: مقارنة SHA-256 للبايتات الخام لملف JSON.
- النسخة المؤقتة استخدمت LF بينما checkout المحلي على Windows قد يستخدم CRLF.
- محتوى JSON كان متطابقاً، لكن بصمة البايتات اختلفت.
- أصبحت المقارنة تستخدم تمثيل JSON معيارياً ثابتاً ومستقلاً عن LF/CRLF.
- بقيت بصمة التدقيق الأصلية والقرارات الـ22 دون تغيير.
- أضيفت اختبارات صريحة لاختلاف LF وCRLF.
- لم تتغير سياسة التفويض أو بوابة الأدلة أو حالة تشغيل المزود.

الحالة:

- PUBLISHED_INGESTION_COMMIT = 5b12978cc95dacf0c1dfa85f17bc1a692c0e3e23
- SOURCE_COUNT = 22
- JSON_HASH_EOL_INDEPENDENT = YES
- EVIDENCE_DECISIONS_CHANGED = NO
- SOURCE_AUTHENTICATION_COMPLETE = NO
- EVENT_BINDING_COMPLETE = NO
- CURRENT_EVIDENCE_GATE = WITHHELD
- RUNWARE_LIVE_EXECUTION = BLOCKED

========================================================
ADAM DELEGATED EVIDENCE ADJUDICATION V1 — 2026-07-28
========================================================

تم تنفيذ العمل المشمول بتفويض المستخدم:

✓ إتمام البحث في المصادر الحديثية الـ11.
✓ اعتماد 8 مصادر حديثية روتينية ضمن التفويض.
✓ إبقاء 3 مصادر بالغة الأهمية للقرار البشري النهائي.
✓ اعتماد نطاق 8 أحداث روتينية.
✓ عزل 6 أحداث تفسيرية/حديثية حساسة في ملف مراجعة مركز.
✓ إعداد توصيات آمنة مكتملة للمصادر والأحداث الحساسة.
✓ عدم تعديل ملف الاعتماد البشري الأصلي للمصادر.
✓ عدم فتح بوابة الأدلة أو تشغيل المزود.

الحالة:

- HADITH_SOURCE_COUNT = 11
- DELEGATED_SOURCE_COUNT = 8
- HIGH_IMPORTANCE_SOURCE_COUNT = 3
- SOURCE_AUTHENTICATION_RESEARCH_COMPLETE = YES
- ROUTINE_SOURCE_DECISIONS_COMPLETE = YES
- ROUTINE_EVENT_SCOPE_APPROVED = 8
- HIGH_IMPORTANCE_EVENT_COUNT = 6
- HIGH_IMPORTANCE_RECOMMENDATIONS_COMPLETE = YES
- FINAL_USER_HIGH_IMPORTANCE_DECISIONS_COMPLETE = NO
- FULL_EPISODE_ADJUDICATION_COMPLETE = NO
- CURRENT_EVIDENCE_GATE = WITHHELD
- RUNWARE_LIVE_EXECUTION = BLOCKED

الخطوة التالية:

تحويل ملف المراجعة المركزة إلى اعتماد بشري واحد للمسائل الحساسة الست،
ثم تركيب حزمة الأدلة النهائية دون إعادة مراجعة الأدلة الروتينية.

========================================================
ADAM HIGH-IMPORTANCE EVIDENCE RESOLUTION V1 — 2026-07-28
========================================================

تم تسجيل القرارات البشرية الصريحة للمسائل الحساسة:

✓ اعتماد أن القلم أول مخلوق بنص الحديث دون إبهام السرد.
✓ اعتماد ذكر وجود إبليس قبل بدء خلق آدم بصيغة غير جازمة فقط.
✓ اعتماد أوصاف مادة خلق آدم دون جدول زمني جازم.
✓ اعتماد النص القرآني في تعليم الأسماء، مع السماح بأقوال المفسرين
  أو الإسرائيليات منسوبةً بلا جزم وبوسم صريح.
✓ اعتماد حديث استخراج الذرية بصياغة مؤهلة لا تجعله التفسير الوحيد للميثاق.
✓ استعادة الاعتماد السابق: زوج آدم هي حواء، وحواء خُلقت من ضلع آدم
  كاستنتاج مدعوم بأحاديث الاسم والضلع الصحيحة.
✓ إبقاء تفاصيل الضلع الأيسر والنوم والتئام الموضع والحوار وسبب التسمية
  منسوبةً للتفسير أو الإسرائيليات بلا جزم.
✓ إكمال تحكيم نطاق الأحداث الخارجية الـ14.
✓ عدم فتح بوابة الأدلة أو تشغيل المزود.

الحالة:

- HIGH_IMPORTANCE_SOURCE_DECISIONS = 3
- HIGH_IMPORTANCE_EVENT_DECISIONS = 6
- PEN_FIRSTNESS = ASSERTIVE_BY_EXPLICIT_HADITH_TEXT
- EXTERNAL_EVENT_SCOPE_COMPLETE = YES
- EXTERNAL_EVENT_COUNT = 14
- KNOWN_EPISODE_EVENT_COUNT = 37
- REMAINING_EPISODE_EVENT_INTEGRATION_REQUIRED = YES
- FULL_EPISODE_ADJUDICATION_COMPLETE = NO
- CURRENT_EVIDENCE_GATE = WITHHELD
- RUNWARE_LIVE_EXECUTION = BLOCKED

الخطوة التالية:

دمج هذا التحكيم مع الأحداث القرآنية الصريحة واعتمادات فجوات الحلقة،
ثم بناء مرشح حزمة الأدلة النهائية دون إعادة مراجعة القرارات المحسومة.

========================================================
ADAM FULL-EPISODE EVIDENCE CANDIDATE V1 — 2026-07-28
========================================================

تم دمج نطاق الحلقة الكامل:

✓ 19 حدثًا قرآنيًا صريحًا مع المواضع والبصمات.
✓ 14 حدثًا بالمصادر الخارجية بعد التحكيم الروتيني والبشري.
✓ 3 أحداث من اعتمادات فجوات الحلقة السابقة: 031 و071 و091.
✓ حسم EV-ADAM-099 بوصفه انتقالًا تحريريًا فقط بلا تقرير واقعة جديدة.
✓ تغطية الأحداث المطلوبة الـ37 بالترتيب المعتمد.
✓ إنشاء مرشح حزمة المصادر.
✓ إنشاء مرشح حزمة الأدلة.
✓ إنشاء مرشح تحكيم الأحداث الـ37.
✓ التحقق من عدم وجود أدلة يتيمة أو معاد استخدامها بين الأحداث.
✓ إنشاء طلب اعتماد نهائي ببصمات المرشحات وعبارة اعتماد واحدة.
✓ عدم إنشاء اعتماد بشري نيابة عن المستخدم.
✓ عدم فتح بوابة الأدلة أو تشغيل أي مزود.
✓ عزل اختبار CLI القديم الذي كان يكتب fixture من 4 أحداث فوق event-map.json الحقيقي.
✓ تشغيل المجموعة الكاملة مرتين مع مقارنة حالة Git قبل الاختبارات وبعدها لمنع أي تلوث للمستودع.

الحالة:

- EVENT_COUNT = 37
- QURAN_EVENT_COUNT = 19
- EXTERNAL_EVENT_COUNT = 14
- GAP_HUMAN_EVENT_COUNT = 3
- EDITORIAL_EVENT_COUNT = 1
- FULL_EPISODE_EVENT_SCOPE_COMPLETE = YES
- CANDIDATE_CONTRACT_VALIDATION = PASS
- FINAL_HUMAN_PACKAGE_APPROVAL = NO
- APPROVED_EVIDENCE_PACKAGE_COMPLETE = NO
- CURRENT_EVIDENCE_GATE = WITHHELD
- RUNWARE_LIVE_EXECUTION = BLOCKED

الخطوة التالية:

بعد اعتماد المستخدم العبارة الدقيقة المرتبطة ببصمات المرشحات، تُحوّل
الملفات إلى حزمة مصادر وأدلة وتحكيم معتمدة، ثم يُشغّل الربط الصارم
غير المتصل لفتح بوابة الأدلة مع استمرار حظر Runware والتنفيذ المدفوع.

========================================================
ADAM FINAL EVIDENCE APPROVAL AND STRICT BINDING V1 — 2026-07-29
========================================================

تم تنفيذ الاعتماد البشري النهائي والربط الصارم دفعة واحدة:

✓ تسجيل عبارة اعتماد المستخدم حرفيًا.
✓ تثبيت البصمات المعتمدة لمرشح المصادر والأدلة وتحكيم الأحداث.
✓ تسجيل توقيت الاعتماد البشري وفق Asia/Baghdad.
✓ تسجيل توقيت UTC المقابل المطلوب تقنيًا من المدقق الصارم.
✓ تحويل 44 مصدرًا إلى حزمة مصادر معتمدة.
✓ تحويل 57 عنصر دليل إلى حزمة أدلة معتمدة.
✓ تحويل قرارات الأحداث الـ37 إلى تحكيم بشري معتمد.
✓ تشغيل ApprovedEvidenceBinder ربطًا صارمًا غير متصل.
✓ فتح بوابة الأدلة بعد نجاح الربط فقط.
✓ الحفاظ على حظر Runware والتنفيذ المباشر والمدفوع والحي.
✓ ربط الأدلة بالمخطط السينمائي ذي الإطارات الـ14.
✓ تسجيل إيصال ربط بالبصمات والمعرفات النهائية.
✓ تحديث عقد الحلقة ومسارات الحزم وبصماتها.
✓ اعتماد Asia/Baghdad منطقة زمنية بشرية مرجعية للمشروع.
✓ تثبيت هوية SIRAJ كمسلسل تاريخي سينمائي ملحمي عالمي المستوى.
✓ منع الأسلوب الوثائقي الجاف والمحاضرة وعرض الشرائح والمونتاج العام.
✓ إبقاء الأدلة عمودًا فقريًا للحقيقة لا قيدًا على القوة السينمائية.

الحالة:

- HUMAN_FINAL_EVIDENCE_APPROVAL = YES
- SOURCE_COUNT = 44
- EVIDENCE_ITEM_COUNT = 57
- ADJUDICATION_DECISION_COUNT = 37
- INCLUDED_EVENT_COUNT = 36
- QUALIFIED_EVENT_COUNT = 7
- OMITTED_EVENT_COUNT = 0
- EDITORIAL_EVENT_COUNT = 1
- STORYBOARD_FRAME_COUNT = 14
- EVIDENCE_GATE_STATUS = OPEN_APPROVED_EVIDENCE_PACKAGE_BOUND
- LIVE_EXECUTION_STATUS = BLOCKED
- RUNWARE_EXECUTION_STATUS = BLOCKED
- PAID_EXECUTION = BLOCKED
- CANONICAL_TIMEZONE = Asia/Baghdad
- FORMAT_IDENTITY = PRESTIGE_HISTORICAL_CINEMATIC_SERIES
- DOCUMENTARY_PRESENTATION_STYLE = FORBIDDEN

الخطوة التالية:

بناء النص السينمائي الكامل للحلقة والستوريبورد التفصيلي المرتبط بالأدلة،
وفق قوس درامي ملحمي، ولغة بصرية وصوتية مؤلفة، وإيقاع مسلسل تاريخي
سينمائي رفيع، ثم تقديمهما في حزمة اعتماد بشرية واحدة.

========================================================
ADAM PRESTIGE CINEMATIC SCRIPT AND STORYBOARD V1 — 2026-07-29
========================================================

تم بناء النص السينمائي والستوريبورد التفصيلي الكامل للحلقة:

✓ نص عربي سينمائي كامل لحلقة مدتها 22 دقيقة.
✓ 14 تسلسلًا دراميًا مرتبطة بالمخطط السينمائي المعتمد.
✓ 70 لقطة موقّتة بالتكوين والكاميرا والحركة والإضاءة والصوت والانتقال.
✓ قوس درامي: الغموض، الاتساع الكوني، الخلق، التكريم، العلم،
  الأمر، الطاعة والكبر، الأنس، الجنة، واقتراب الاختبار.
✓ تغطية أحداث الحلقة الـ37 كاملة.
✓ تغطية عناصر الأدلة الـ57 كاملة.
✓ تثبيت عبارات التأهيل للأحداث السبعة المؤهلة.
✓ منع اختلاق الحوارات التاريخية.
✓ منع التجسيد الحرفي لله والملائكة والأنبياء وإبليس والغيب.
✓ اعتماد المعالجة الرمزية والبيئية غير الجازمة بوصفها أداة سينمائية.
✓ تصميم صوت وموسيقى وانتقالات مؤلفة لكل تسلسل.
✓ تثبيت Asia/Baghdad توقيتًا مرجعيًا.
✓ إبقاء Runware والتنفيذ الحي والمباشر والمدفوع محظورًا.
✓ عدم جدولة أي ثانية فيديو مولد قبل الاعتماد البشري.
✓ إنشاء طلب اعتماد بشري واحد مرتبط ببصمتي النص والستوريبورد.
✓ إصلاح مدقق الاعتماد السابق كي يحمي حقول الربط من دون إعادة المرحلة اللاحقة إلى الوراء.
✓ حفظ حقول النص والستوريبورد وطلب الاعتماد ومرحلة next_stage عند إعادة تدقيق الربط.

الحالة:

- FORMAT_IDENTITY = PRESTIGE_HISTORICAL_CINEMATIC_SERIES
- EPISODE_DURATION_SECONDS = 1320
- SEQUENCE_COUNT = 14
- SHOT_COUNT = 70
- EVENT_TRACE_COUNT = 37
- EVIDENCE_TRACE_COUNT = 57
- EVENT_COVERAGE_COMPLETE = YES
- EVIDENCE_COVERAGE_COMPLETE = YES
- HUMAN_SCRIPT_APPROVAL = NO
- RELIGIOUS_SAFETY_APPROVAL = NO
- HUMAN_STORYBOARD_APPROVAL = NO
- MASTER_VISUAL_APPROVAL = NO
- LIVE_EXECUTION_STATUS = BLOCKED
- PAID_EXECUTION = BLOCKED
- GENERATED_VIDEO_PLANNED_SECONDS = 0
- CANONICAL_TIMEZONE = Asia/Baghdad

الخطوة التالية:

مراجعة المستخدم للنص والستوريبورد في حزمة واحدة. بعد الاعتماد، يبدأ
تصميم الهوية البصرية الرئيسية والأنيماتيك غير المدفوع، ثم تأتي بوابة
مستقلة لأي اختبار مزود أو تنفيذ مدفوع.

========================================================
ADAM PRESTIGE CINEMATIC DIRECTOR'S CUT V2 — 2026-07-29
========================================================

تم تنفيذ التوجيه الإبداعي الجديد للمستخدم:

✓ حفظ معنى كل معلومة ودرجة الجزم بها.
✓ التحرر من السياق والصياغة الحرفية للمصادر في العرض الفني.
✓ تحويل المعلومة إلى فعل درامي وصورة وصوت وإيقاع وانتقال.
✓ إزالة لغة المنهج البحثي من التعليق الصوتي.
✓ إزالة افتتاحية «نحن لا نبحث» وكل التقديم الميتا.
✓ دمج التأهيلات العلمية داخل اللغة الدرامية والبطاقات البصرية.
✓ بدء الحلقة من قلب السجود والرفض بدل مقدمة تفسيرية طويلة.
✓ بناء بيئات مادية حية: الماء البدئي، الأرض، الطقس، الطين،
  الوديان، الجنة، التاريخ البشري، والآثار البيئية.
✓ تقليل الاعتماد على التجريد والموشن غرافيك بوصفهما اللغة الأساسية.
✓ إنشاء 14 تسلسلًا إخراجيًا و70 لقطة موقّتة بمجموع 1320 ثانية.
✓ الحفاظ على تتبع الأحداث الـ37 وعناصر الأدلة الـ57.
✓ الحفاظ على التأهيلات السبعة وعدم تحويلها إلى جزم.
✓ حفظ نسخة v1 كأثر تدقيقي superseded وعدم حذفها.
✓ إصلاح مدقق v1 كي لا يعيد episode-definition إلى الوراء.
✓ جعل تحديث episode-definition الخاص بالنسخة الإخراجية الثانية حتميًا وقابلًا لإعادة البناء دون تغيير.
✓ منع إعادة التقاط نسخة v2 بوصفها النسخة v1 المستبدلة عند التشغيل الثاني.
✓ استمرار حظر Runware والتنفيذ المباشر والحي والمدفوع.

الحالة:

- DIRECTORS_CUT_VERSION = 2
- ADAPTATION_POLICY =
  MEANING_PRESERVED_WORDING_CINEMATICALLY_ADAPTED
- SOURCE_CONTEXT_LITERALISM = REMOVED
- RESEARCH_META_LANGUAGE_IN_NARRATION = REMOVED
- EPISODE_DURATION_SECONDS = 1320
- SEQUENCE_COUNT = 14
- SHOT_COUNT = 70
- NARRATION_WORD_COUNT = 1321
- EVENT_TRACE_COUNT = 37
- EVIDENCE_TRACE_COUNT = 57
- HUMAN_SCRIPT_APPROVAL = NO
- HUMAN_STORYBOARD_APPROVAL = NO
- LIVE_EXECUTION_STATUS = BLOCKED
- PAID_EXECUTION = BLOCKED
- RUNWARE_EXECUTION = BLOCKED

الخطوة التالية:

مراجعة المستخدم للنسخة الإخراجية الثانية، ثم اعتماد النص والسلامة
الدينية والستوريبورد ببصماتهما قبل تصميم الهوية البصرية الرئيسية
والأنيماتيك غير المدفوع.

========================================================
ADAM FINAL STORYBOARD MASTER V2.1 — 2026-07-29
========================================================

تم إغلاق مرحلة بناء النص والستوريبورد كمرشح نهائي للمراجعة البشرية:

✓ تصحيح نص الميثاق إلى:
  ﴿أَلَسْتُ بِرَبِّكُمْ قَالُوا بَلَىٰ شَهِدْنَا﴾
✓ تثبيت خروج ذرية آدم من ظهره بصيغة جازمة.
✓ حصر التأهيل في الربط الزمني الدقيق بين خروج الذرية والميثاق فقط.
✓ إعادة صياغة «الميثاق والذرية» بلغة درامية لا بصيغة خبر عابر.
✓ إنهاء تمريرة الحوار النهائية وإزالة البقايا البحثية المباشرة.
✓ تحسين عرض أخبار التفسير في مشاهد إبليس وحواء والشجرة دون تغيير معناها.
✓ تثبيت 14 تسلسلًا و70 لقطة و1320 ثانية.
✓ إضافة نبضة درامية فريدة لكل لقطة: 70/70.
✓ إضافة المعنى البصري الضمني لكل لقطة: 70/70.
✓ إضافة سيكولوجيا الكاميرا ومنطق القطع ومنظور الصوت لكل لقطة: 70/70.
✓ إضافة مرساة الاستمرارية ومعايير القبول وأسباب الرفض لكل لقطة: 70/70.
✓ تثبيت قانون العدسات والحركة والإضاءة واللون والانتقالات والصوت.
✓ إزالة جميع اللقطات العامة أو المؤقتة أو غير المحسومة إخراجيًا.
✓ إنشاء تدقيق إخراجي نهائي مستقل للستوريبورد.
✓ حفظ Director’s Cut v2 كاملًا كأثر تدقيقي superseded.
✓ إصلاح مدقق v2 كي لا يعيد تعريف الحلقة أو مرحلتها إلى الوراء.
✓ توسيع مدقق v1 ليعترف بحالة v2.1 ويحفظها دون خفضها إلى v1 أو v2.
✓ إصلاح محرك v2 كي يبني عرض تدقيق v2 من v2.1 مع حفظ سلف v1 الأصلي.
✓ اختبار سلسلة التوافق الكاملة v1 ← v2 ← v2.1 مباشرة ومنع أي ارتداد.
✓ استمرار حظر Runware والتنفيذ الحي والمباشر والمدفوع.

الحالة:

- DIRECTORS_CUT_VERSION = 2.1
- STORYBOARD_COMPLETION_STATUS =
  COMPLETE_AWAITING_HUMAN_APPROVAL
- EXACT_COVENANT_VERSE = PASS
- DESCENDANTS_EMERGENCE = ASSERTIVE
- CHRONOLOGICAL_LINKAGE = QUALIFIED_ONLY
- SEQUENCE_COUNT = 14
- SHOT_COUNT = 70
- EPISODE_DURATION_SECONDS = 1320
- EVENT_TRACE_COUNT = 37
- EVIDENCE_TRACE_COUNT = 57
- DIRECTORIAL_BEAT_COVERAGE = 70/70
- VISUAL_SUBTEXT_COVERAGE = 70/70
- CAMERA_PSYCHOLOGY_COVERAGE = 70/70
- SOUND_PERSPECTIVE_COVERAGE = 70/70
- ACCEPTANCE_CRITERIA_COVERAGE = 70/70
- GENERIC_PLACEHOLDER_SHOTS = 0
- UNRESOLVED_DIRECTORIAL_DECISIONS = 0
- HUMAN_SCRIPT_APPROVAL = NO
- HUMAN_STORYBOARD_APPROVAL = NO
- LIVE_EXECUTION_STATUS = BLOCKED
- PAID_EXECUTION = BLOCKED
- RUNWARE_EXECUTION = BLOCKED

الخطوة التالية:

المراجعة البشرية النهائية للنص والستوريبورد ببصمتيهما، ثم بناء
الهوية البصرية الرئيسية وColor Script والأنيماتيك غير المدفوع.

========================================================
ADAM FINAL STORYBOARD MASTER HUMAN APPROVAL BINDING V2.1 — 2026-07-29
========================================================

تم استلام وربط عبارة الاعتماد البشرية المطابقة حرفيًا:

«أعتمد بشريًا النسخة الإخراجية النهائية للنص السينمائي والستوريبورد
الرئيسي لحلقة آدم بإصدار 2.1 وفق بصمتيهما المحددتين، وأجيز الانتقال
إلى الهوية البصرية الرئيسية والأنيماتيك غير المدفوع دون السماح بأي
تشغيل مدفوع أو مباشر»

النتائج:

✓ اعتماد النص السينمائي النهائي v2.1.
✓ اعتماد السلامة الدينية للنص النهائي v2.1.
✓ اعتماد الستوريبورد الرئيسي ذي اللقطات السبعين.
✓ ربط الاعتماد ببصمة النص:
  ff540783ec519581bd902caf81145c3f77819a7351f2bd5d07e9f84705a4fb27
✓ ربط الاعتماد ببصمة الستوريبورد:
  867b88ade164ebe444aeaaeeb9f60accef122f59cf8b45b020223f3ca8788bf8
✓ إصدار سجل اعتماد بشري مستقل.
✓ إصدار إيصال ربط مستقل.
✓ إصدار عقد ربط نهائي.
✓ فتح بوابة العمل غير المدفوع للهوية البصرية وColor Script والأنيماتيك.
✓ إبقاء اعتماد الهوية البصرية الرئيسية نفسها معلقًا.
✓ إبقاء Runware وكل تشغيل حي أو مباشر أو مدفوع محظورًا.
✓ جعل مدقق Storyboard Master v2.1 يحفظ حالة الاعتماد اللاحقة.
✓ مطابقة ربط الاعتماد مع بنية ملف التدقيق الإخراجي المحفوظة فعليًا.
✓ اشتقاق انعدام القرارات الإخراجية العالقة من تغطية 70/70 وصفر لقطات عامة بدل طلب حقل اصطناعي غير محفوظ.
✓ إضافة اختبار صريح لقبول ملف التدقيق الحقيقي ومنع الانحدار.
✓ توحيد قيود التنفيذ في المستوى الأعلى لكل من سجل الاعتماد والإيصال والعقد وبوابة التطوير البصري.
✓ تثبيت live/paid/direct/Runware = BLOCKED في جميع آثار الربط.
✓ تشغيل مسار build → update → validate كاملًا قبل أي Git operation.
✓ استمرار عمل سلسلة التدقيق v1 ← v2 ← v2.1 دون ارتداد.

الحالة:

- HUMAN_SCRIPT_APPROVAL = YES
- RELIGIOUS_SAFETY_APPROVAL = YES
- HUMAN_STORYBOARD_APPROVAL = YES
- STORYBOARD_COMPLETION_STATUS = COMPLETE_HUMAN_APPROVED
- MASTER_VISUAL_APPROVAL = NO
- NON_PAID_VISUAL_DEVELOPMENT_GATE = OPEN
- LIVE_EXECUTION_STATUS = BLOCKED
- PAID_EXECUTION = BLOCKED
- DIRECT_EXECUTION = BLOCKED
- RUNWARE_EXECUTION = BLOCKED
- GENERATED_VIDEO_PLANNED_SECONDS = 0

المرحلة التالية:

MASTER_VISUAL_BIBLE_COLOR_SCRIPT_AND_NON_PAID_ANIMATIC_DEVELOPMENT

========================================================
ADAM MASTER VISUAL DEVELOPMENT V1 — 2026-07-29
========================================================

تم بناء حزمة التطوير البصري غير المدفوع انطلاقًا من النص والستوريبورد
المعتمدين بشريًا بإصدار 2.1، من دون إنشاء أي أصل مرئي أو صوتي أو فيديو.

النتائج:

✓ Master Visual Bible يغطي 14/14 تسلسلًا و70/70 لقطة.
✓ Color Script يغطي مدة الحلقة الكاملة البالغة 1320 ثانية.
✓ خطة Animatic نصية وهندسية غير مدفوعة تغطي 70/70 لقطة.
✓ خريطة Audio Previs نصية بلا توليد صوت.
✓ تدقيق وربط حتميان ببصمتي النص والستوريبورد المعتمدتين.
✓ حماية أدوات Storyboard/Approval السابقة من إرجاع الحالة إلى الخلف.
✓ إبقاء اعتماد الهوية البصرية الرئيسية معلقًا للمراجعة البشرية.
✓ إبقاء live/paid/direct/Runware = BLOCKED.
✓ إبقاء GENERATED_VIDEO_PLANNED_SECONDS = 0.

الحالة:

- MASTER_VISUAL_BIBLE_STATUS = DEVELOPED_AWAITING_HUMAN_APPROVAL
- COLOR_SCRIPT_STATUS = COMPLETE_NON_PAID_DEVELOPMENT_AWAITING_HUMAN_APPROVAL
- NON_PAID_ANIMATIC_STATUS = PLANNED_NON_PAID_NO_MEDIA_EXECUTION
- MASTER_VISUAL_APPROVAL = NO
- MEDIA_ASSETS_CREATED = 0
- LIVE_EXECUTION_STATUS = BLOCKED
- PAID_EXECUTION = BLOCKED
- DIRECT_EXECUTION = BLOCKED
- RUNWARE_EXECUTION = BLOCKED

المرحلة التالية:

HUMAN_REVIEW_OF_MASTER_VISUAL_BIBLE_COLOR_SCRIPT_AND_NON_PAID_ANIMATIC_V1

========================================================
ADAM MASTER VISUAL HUMAN REVIEW V1 — 2026-07-29
========================================================

تمت مراجعة حزمة Master Visual Bible وColor Script وخطة Animatic النصية
مراجعة بشرية-القرار آليّة البناء، من دون منح أي اعتماد تلقائي أو إنشاء وسائط.

النتائج:

✓ حزمة مراجعة قابلة للقراءة تغطي 14/14 تسلسلًا و70/70 لقطة.
✓ مراجعة نقدية تفصل بين صلاحية خط الأساس وعدم أهلية الاعتماد البصري النهائي.
✓ صفر عوائق أمام عرض خط الأساس للقرار البشري.
✓ ثلاثة عوائق مقصودة أمام الاعتماد البصري النهائي: غياب Style Frames،
  غياب Color Swatches المعايرة، وغياب Animatic مرئي موقّت.
✓ خطة ثمانية Style Frames/Keyframes مرجعية غير مدفوعة، غير منفذة بعد.
✓ طلب اعتماد بشري بعبارة دقيقة وبصمة SHA-256.
✓ حماية مراحل Storyboard/Approval/Visual Development السابقة من الارتداد.
✓ إبقاء MASTER_VISUAL_APPROVAL = NO.
✓ إبقاء MEDIA_ASSETS_CREATED = 0.
✓ إبقاء live/paid/direct/Runware = BLOCKED.
✓ إبقاء GENERATED_VIDEO_PLANNED_SECONDS = 0.

الحالة:

- REVIEW_DOSSIER_STATUS = READY_FOR_HUMAN_DECISION_ON_DEVELOPMENT_BASELINE
- CRITICAL_REVIEW_STATUS = PASS_REVIEW_READY_WITH_FINAL_APPROVAL_BLOCKERS
- STYLE_FRAME_IMAGE_AUTHORISATION = PENDING_HUMAN_APPROVAL
- HUMAN_DECISION = PENDING
- FINAL_MASTER_VISUAL_APPROVAL_ELIGIBLE = NO

المرحلة التالية:

HUMAN_DECISION_ON_MASTER_VISUAL_DEVELOPMENT_REVIEW_V1

========================================================
ADAM MASTER VISUAL HUMAN APPROVAL BINDING V1 — 2026-07-29
========================================================

تم تسجيل الموافقة البشرية الدقيقة على خط أساس التطوير البصري لحلقة آدم.

النتائج:

✓ اعتماد خط أساس التطوير البصري فقط.
✓ فتح بوابة ثمانية Style Frames/Keyframes ثابتة وغير مدفوعة ومحددة مسبقًا.
✓ إنشاء Approval Record وReceipt وBinding وPrototype Gate حتمية.
✓ عدم اعتماد الهوية البصرية الرئيسية النهائية.
✓ منع الصوت والفيديو والـAnimatic الموقّت.
✓ إبقاء live/paid/direct/Runware = BLOCKED.
✓ إبقاء GENERATED_VIDEO_PLANNED_SECONDS = 0.

المرحلة التالية:

NON_PAID_MASTER_STYLE_FRAMES_AND_KEYFRAME_PROTOTYPING_V1

============================================================
ADAM PRELIMINARY STYLE-FRAME REFERENCE SET V1 — 2026-07-29
============================================================

تم تثبيت ثماني صور وافق عليها المستخدم بشريًا كمرجع اتجاه فني مبدئي قابل للتعديل.

النتائج:

✓ ثماني صور PNG مثبتة ببصمات SHA-256 وأسماء مستقرة.
✓ اعتماد مبدئي للاتجاه الفني فقط، دون اعتماد نهائي للهوية البصرية.
✓ عدم الادعاء بأن الصور ربط نهائي بلقطات الستوريبورد.
✓ تثبيت قواعد منع تجسيد الملائكة، ومنع إظهار بشرة المرأة، وحجب ملامح الأنبياء.
✓ تثبيت منع تصوير الأنبياء كأجساد كاملة بعد الهبوط إلا لضرورة نصية محددة لعضو ذي أهمية.
✓ تثبيت منع الجفاف والفناء والنقص في تصوير الجنة.
✓ فتح بوابة نموذج حركة واحد غير مدفوع من صورة بيئية خالية من الأشخاص.
✓ مدة النموذج 8–12 ثانية، بلا صوت أو موسيقى أو حوار.
✓ إبقاء full episode / paid / live / direct / Runware = BLOCKED.
✓ إبقاء MASTER_VISUAL_APPROVAL = NO.

المرحلة التشغيلية التالية:

NON_PAID_SINGLE_SHOT_MOTION_PROTOTYPE_V1


============================================================
ADAM VEO PRODUCTION MANIFEST V1 — 2026-08-04
============================================================

تم تثبيت سياسة السلامة البصرية v2 وبيان إنتاج Veo 3.1 Lite للقطات الحلقة السبعين.

النتائج:

✓ منع التبرج للنساء، ومنع ظهور الشعر.
✓ السماح عند الضرورة بالكفين أو القدمين أو جزء محدود غير مكتمل من ملامح الوجه.
✓ منع الوجه الكامل الواضح أو القابل للتعرف لأي شخصية.
✓ تثبيت قيود آدم قبل الهبوط وبعده.
✓ اعتماد google:veo@3.1-lite بوصفه نموذج الفيديو الأساسي عبر Runware.
✓ تصنيف 70 لقطة: 29 Image-to-Video، 10 Text-to-Video، 25 Compositing، 6 Graphics.
✓ إبقاء التنفيذ المدفوع الآلي وإنتاج الحلقة دفعة واحدة محظورين.
✓ فتح مرحلة تأليف Shot Packages فقط.

السياسة:
adam_visual_safety_policy_v2_2a7c860f00834840

بيان الإنتاج:
adam_veo_production_manifest_v1_83ce0eb05bd48993

المرحلة التالية:
VEO_SHOT_PACKAGE_AUTHORING_V1


============================================================
ADAM VEO SHOT PACK 001 — 2026-08-04
============================================================

تم تأليف حزمة اللقطة الأولى لمسار Veo:

Shot:
ADAM-DC2-S02-SH03

Package:
adam_veo_shot_pack_001_v1_afe8d586bc5cf23c

Binding:
adam_veo_shot_pack_001_binding_v1_fd0f2e91dfe37fc4

الحالة:

✓ تم ربط الحزمة ببيان إنتاج Veo وسياسة السلامة البصرية v2.
✓ تم تأليف Beat 01 فقط بوضع Text-to-Video ومدته 8 ثوانٍ.
✓ تم إبقاء Beat 02 مؤجلًا حتى مراجعة ناتج Beat 01 بشريًا.
✓ تم منع التنفيذ المدفوع الآلي واليدوي حتى اعتماد الحزمة بشريًا.
✓ تم تحديد بوابة قبول بدرجة 80/100 مع فشل مانع لأي تجسيد أو تشوه مخالف.
✓ تم استعادة scripts/project_progress/pre_commit_progress_guard.py.
✓ لم يتم توليد أي فيديو ولم يُصرف أي رصيد.

النموذج:
google:veo@3.1-lite

المرحلة التالية:
HUMAN_REVIEW_ADAM_VEO_SHOT_PACK_001_V1



============================================================
SIRAJ DESKTOP DASHBOARD V1 — 2026-08-04
============================================================

تم إنشاء النسخة الأولى من واجهة سطح المكتب لسراج وفق التصور البصري المعتمد بشريًا.

الحالة:

✓ واجهة Windows عربية RTL مبنية بـ PySide6 / Qt Widgets.
✓ لوحة تحكم فعلية تقرأ بيانات projects/episode-* من المستودع.
✓ إضافة قسم الحلقات الجاهزة للتحويل إلى فيديو جاهز للنشر على يوتيوب.
✓ إضافة المعاينة، مسار الإنتاج، المخرجات، سجل التنفيذ، المقاييس والنشاطات.
✓ عدم استخدام حلقات تجريبية أو حالات نشر وهمية.
✓ إبقاء توليد الفيديو المدفوع محجوبًا في V1.
✓ حفظ التصور البصري المعتمد وربطه بإثبات الموافقة البشرية.
✓ إضافة اختبارات مستقلة ومدقق fast-track.

تقنية الواجهة:
PySide6>=6.10,<7

المرحلة التالية:
LOCAL_PYSIDE6_INSTALL_AND_HUMAN_UI_REVIEW



============================================================
SIRAJ DESKTOP DASHBOARD V1.1 — 2026-08-04
============================================================

تم تنفيذ جولة التصحيح الأولى لواجهة سطح المكتب بعد المراجعة البشرية المباشرة.

النتائج:

✓ فصل الحلقات الجاهزة للتحويل عن الحلقات قيد العمل.
✓ إضافة حالة فارغة صحيحة عند عدم وجود حلقة جاهزة.
✓ إصلاح احتساب PLANNED_NOT_GENERATED حتى لا يعد مقطعًا منتجًا.
✓ فصل اللقطات المخططة والمقاطع المنتجة واللقطات المعتمدة.
✓ إضافة QSplitter متجاوب بين مساحة العمل وعمود المعاينة.
✓ منع التمرير الأفقي في مساحة العمل والجداول والسجل.
✓ تثبيت المعاينة على نسبة 16:9 مع عرض اللقطة ووحدة التوليد وحالة الفيديو.
✓ قراءة Beat الحالي من أحدث Shot Package.
✓ استبدال الرموز المختلطة بأيقونات SVG داخلية موحدة.
✓ ربط شريط سير العمل بحالة الحلقة الفعلية.
✓ حفظ لقطة المراجعة البشرية وربطها بإصدار v1.1.
✓ بقي تنفيذ Runware المدفوع محجوبًا بالكامل.

المرحلة التالية:
HUMAN_UI_REVIEW_V1_1_AND_RUNWARE_EXECUTION_BINDING


============================================================
SIRAJ DESKTOP DASHBOARD V1.2 — 2026-08-04
============================================================

تم نشر جولة التصحيح البصري v1.2 لواجهة سطح مكتب سراج.

النتائج الملزمة:

✓ إعادة رأس المشروع المدمج وإبقاؤه خارج منطقة التمرير.
✓ ضمان ظهور لوحة المعاينة وCanvas بنسبة 16:9 عند 1366×768.
✓ عرض أسماء ملفات المخرجات فقط مع Tooltip للمسار الكامل وزر فتح.
✓ دعم التفاف نص النشاطات الأخيرة دون تمرير أفقي.
✓ استمرار فصل الحلقات الجاهزة عن الحلقات قيد العمل.
✓ استمرار منع التمرير الأفقي.
✓ استمرار حجب التنفيذ المدفوع عبر Runware.
✓ لم يتم توليد فيديو ولم يُصرف رصيد.

الإصدار:
SIRAJ_DESKTOP_DASHBOARD_V1_2

المرحلة التالية:
HUMAN_UI_REVIEW_V1_2_AND_RUNWARE_EXECUTION_BINDING


============================================================
SIRAJ DESKTOP DASHBOARD V1.3 — 2026-08-05
============================================================

تم إصلاح الانهيار الرأسي في واجهة سطح مكتب سراج.

النتائج الملزمة:

✓ إزالة QScrollArea المشترك الذي كان يضغط العمودين رأسيًا.
✓ إضافة تمرير رأسي مستقل للعمود الرئيسي وعمود المعاينة.
✓ إبقاء لوحة الحلقات ظاهرة أعلى العمود الرئيسي.
✓ إبقاء عنوان المعاينة وحالتها وCanvas بنسبة 16:9 ظاهرة أعلى العمود الأيمن.
✓ فحص الجزء المرئي فعليًا داخل viewport بدل أبعاد Widget النظرية فقط.
✓ إضافة اختبارات بكسلية إلى لقطات المعاينة ولوحة الحلقات.
✓ استمرار منع التمرير الأفقي.
✓ لم يتم توليد فيديو ولم يُصرف أي رصيد.
✓ تنفيذ Runware المدفوع ما زال محجوبًا.

الإصدار:
SIRAJ_DESKTOP_DASHBOARD_V1_3

المرحلة التالية:
HUMAN_UI_REVIEW_V1_3_AND_RUNWARE_EXECUTION_BINDING


============================================================
SIRAJ DESKTOP PRODUCTION CONSOLE V1 — 2026-08-05
============================================================

تم تحويل واجهة سطح المكتب من لوحة عرض فقط إلى بوابة تشغيل ومراجعة
لأول وحدة توليد فعلية من حلقة آدم.

النطاق المعتمد:

✓ الحلقة: episode-001-adam
✓ اللقطة: ADAM-DC2-S02-SH03
✓ الوحدة: ADAM-DC2-S02-SH03-B01
✓ النموذج: google:veo@3.1-lite
✓ 8 ثوانٍ، 1280×720، MP4، دون صوت
✓ محاولة videoInference واحدة فقط
✓ سقف التكلفة المصرح: 0.40 USD
✓ التنفيذ يبدأ حصريًا بضغط المستخدم داخل واجهة سطح المكتب
✓ إنشاء قفل دائم قبل الاتصال بالشبكة لمنع التكرار
✓ الاستعادة تستعلم عن taskUUID نفسه ولا تعيد الإرسال
✓ تنزيل MP4 وحساب SHA-256 وتسجيل إيصال التنفيذ
✓ إدخال المراجعة البشرية الموزونة وحفظ PASS/FAIL داخل الواجهة
✓ إبقاء Beat 02 والتوليد الشامل وإعادة المحاولة التلقائية محظورة
✓ عدم حفظ RUNWARE_API_KEY في الملفات أو السجلات أو Git

الناشر والمدقق والاختبارات لا ينفذون أي طلب Runware ولا يصرفون رصيدًا.

المرحلة التالية:
USER_OPERATED_DESKTOP_BEAT_01_EXECUTION


============================================================
SIRAJ DESKTOP AUTOMATIC VIDEO V1 — 2026-08-05
============================================================

تم تبسيط تشغيل الفيديو من واجهة سطح المكتب إلى عقد تشغيل بشري صغير:

1) الضغط على زر «إنشاء الفيديو».
2) بعد اكتمال الملف، إدخال تقييم نهائي واحد فقط من 0 إلى 100.

تنفذ الواجهة تلقائيًا بعد الضغط:

✓ التحقق من حالة المحاولة
✓ استعادة taskUUID القائم عند الانقطاع دون إعادة الإرسال
✓ إرسال videoInference واحد لكل ضغطة صريحة
✓ متابعة Runware غير المتزامنة
✓ تنزيل MP4
✓ حساب SHA-256
✓ تسجيل التكلفة والـseed والإيصال
✓ إظهار زر «عرض الفيديو»
✓ إظهار زر «عرض مكانه في الجهاز»

عقد التقييم:

✓ مدخل وحيد: عدد صحيح من 0 إلى 100
✓ 80–100 = PASS
✓ 0–79 = FAIL وتجهيز المحاولة التالية
✓ لا درجات فئوية ولا ملاحظات إلزامية ولا قائمة عيوب مانعة

سياسة الإنفاق:

✓ لا إعادة محاولة مدفوعة في الخلفية
✓ كل طلب مدفوع يحتاج ضغطة جديدة على «إنشاء الفيديو»
✓ ثلاث خطط متدرجة كحد أقصى
✓ سقف مسجل قدره 0.40 USD لكل محاولة
✓ حفظ المفتاح في Windows Credential Manager فقط
✓ لا حفظ للمفتاح داخل المشروع أو Git

يتم استيراد ناتج V1 الموجود محليًا تلقائيًا كمحاولة أولى، ثم تنتظر
الواجهة تقييمه الرقمي فقط.

المرحلة التالية:
USER_ONE_CLICK_VIDEO_GENERATION_AND_SINGLE_SCORE_REVIEW


============================================================
SIRAJ EPISODE PRODUCTION CONTROL V1 — 2026-08-05
============================================================

تم تثبيت قواعد إنتاج الحلقات الملزمة داخل النظام:

✓ الحد الأقصى الكامل للحلقة = 40.00 USD
✓ لا هامش إضافي ولا صلاحية لتجاوز السقف
✓ فحص الميزانية قبل كل طلب مدفوع جديد
✓ احتساب المصروف الفعلي من الإيصالات مع إزالة التكرار حسب taskUUID
✓ حجب الطلب قبل الإرسال إذا تجاوزت الكلفة المتوقعة سقف الحلقة

الخطة الهجينة لحلقة آدم:

✓ 70 لقطة مونتاجية
✓ 20 لقطة فيديو مولد
✓ 160 ثانية فيديو مولد مخطط
✓ النطاق الملزم 120–180 ثانية
✓ 44 لقطة صورة متحركة وتركيب بصري
✓ 6 لقطات جرافيك
✓ السبعون لقطة ليست سبعين عملية توليد فيديو

قانون الصوت:

✓ الموسيقى ممنوعة
✓ Musical score ممنوع
✓ الأغاني ممنوعة
✓ المؤثرات الصوتية مسموحة
✓ لا قيد على نوع المؤثر ما دام مناسبًا للمشهد
✓ الصمت المصمم والتعليق الصوتي مسموحان

واجهة سطح المكتب:

✓ تبويب خطة الحلقة
✓ عرض طابور اللقطات السبعين
✓ عرض المصروف والمتبقي من 40$
✓ عرض المعالجة النهائية لكل لقطة
✓ تبويب إنتاج المقطع الحالي
✓ زرا عرض الفيديو وعرض مكان الملف
✓ تقييم بشري واحد من 0 إلى 100
✓ لا إعادة مدفوعة خفية

المرحلة التالية:
AUTHOR_NEXT_QUEUE_SHOT_PACKAGE


============================================================
SIRAJ AUTONOMOUS EPISODE ORCHESTRATOR V1 — 2026-08-05
============================================================

بدأ تنفيذ منسق سراج الذاتي للحلقات.

المنفذ في هذه المرحلة:

✓ زر «إنتاج الحلقة التالية» داخل واجهة سطح المكتب
✓ GPT-5.6 Luna عبر OpenAI Responses API
✓ بحث ويب مدمج عند اقتراح الموضوع والأحداث
✓ مخرجات منظمة وفق JSON Schema صارم
✓ اقتراح 3–15 حدثًا مع الموقف الدليلي والثقة والمراجع
✓ بوابة نقاش بشرية مباشرة مع Luna
✓ اعتماد بشري إلزامي للموضوع والأحداث
✓ إنشاء مساحة الحلقة التالية تلقائيًا بعد الاعتماد
✓ إنشاء سجل مراحل كامل حتى READY_TO_PUBLISH
✓ إنشاء مخطط اعتماديات يضمن التعديل الجزئي فقط
✓ منع إعادة توليد الحلقة كاملة بسبب خلل محلي
✓ حفظ مفتاح OpenAI ومفتاح ElevenLabs في Windows Credential Manager
✓ استمرار Runware كمزود الصور والفيديو

القواعد الثابتة:

✓ سقف الحلقة الكامل 40 USD
✓ الموسيقى ممنوعة
✓ المؤثرات الصوتية المناسبة للمشهد مسموحة
✓ رفع YouTube يدوي
✓ بوابتان بشريتان فقط: النطاق والمراجعة النهائية

حدود الإصدار:

هذه المرحلة تنفذ اختيار الموضوع والأحداث والنقاش والاعتماد وإنشاء بنية الحلقة
ومخطط الاعتماديات. البحث التفصيلي وكتابة النص والستوريبورد وطوابير Runware
وElevenLabs والمونتاج الآلي تبقى المرحلة التالية ولا يتم الادعاء بأنها مكتملة.

NEXT_STAGE=AUTOMATIC_RESEARCH_SCRIPT_STORYBOARD_RUNNER_V1

============================================================
SIRAJ EPISODE COST BREAKDOWN V1 — 2026-08-05
============================================================

تمت إضافة مربع تكلفة الحلقة إلى واجهة سطح المكتب.

✓ إجمالي التكلفة المسجلة لكل حلقة
✓ فصل التكلفة الفعلية عن التقديرية
✓ المتبقي من سقف 40 USD
✓ تفصيل Luna وRunware للصور وRunware للفيديو وElevenLabs والمؤثرات وأخرى
✓ عدد العمليات المدفوعة
✓ إزالة الازدواجية حسب معرّف مهمة المزود
✓ تسجيل تكلفة Luna الخاصة بنطاق الحلقة داخل الحلقة بعد الاعتماد
✓ عدم ترحيل تكلفة Luna من حلقة إلى الحلقة التالية
✓ لا طلبات مدفوعة أثناء النشر أو الاختبار

NEXT_STAGE=AUTOMATIC_RESEARCH_SCRIPT_STORYBOARD_RUNNER_V1

============================================================
AUTOMATIC RESEARCH SCRIPT STORYBOARD RUNNER V1 — 2026-08-05
============================================================

تم تنفيذ السلسلة التحريرية الذاتية بعد اعتماد موضوع الحلقة وأحداثها.

✓ بحث أدلة آلي بواسطة GPT-5.6 Luna مع بحث ويب
✓ حزمة أدلة تربط كل ادعاء بمصدر ومعرف
✓ منع انتقال الادعاءات المستبعدة إلى النص
✓ كتابة النص العربي من الأدلة المعتمدة فقط
✓ ستوريبورد وخطة وسائط من 70 لقطة بالضبط
✓ 20 فيديو مولد × 8 ثوانٍ = 160 ثانية
✓ 44 صورة متحركة/تركيب بصري
✓ 6 لقطات جرافيك
✓ لا بوابة بشرية ثالثة
✓ بدء تلقائي بعد اعتماد النطاق
✓ استئناف صريح بعد الخطأ
✓ لا إعادة مدفوعة خفية
✓ حفظ استجابة المزود قبل اشتقاق المخرج لاستعادتها دون طلب جديد
✓ تحديث سجل المراحل ومخطط الاعتماديات
✓ إيصالات تكلفة منفصلة للبحث والنص والستوريبورد
✓ الموسيقى ممنوعة والمؤثرات المناسبة مسموحة

NEXT_STAGE=RUNWARE_MEDIA_QUEUE_AND_ELEVENLABS_TTS_V1

============================================================
SIRAJ EDITORIAL SOURCE DURATION CONSTITUTION FIX V1 — 2026-08-05
============================================================

تم تصحيح السلسلة التحريرية الذاتية وفق دستور سراج:

✓ كتب المكتبة الشاملة المختارة هي مصدر المعلومات الأول.
✓ الإنترنت مصدر ثانوي لسد الفجوات فقط.
✓ يمنع الطلب المدفوع للبحث إذا لم يتوفر سياق محلي كافٍ من الشاملة.
✓ اقتراح نطاق الحلقة يستخدم فهرس الشاملة قبل الويب.
✓ مدة الحلقة من 18 إلى 25 دقيقة.
✓ الهدف التحريري 22 دقيقة.
✓ النص والتحقق يفرضان 1080–1500 ثانية.
✓ لا طلبات مدفوعة أثناء النشر أو الاختبار.
✓ البوابتان البشريتان فقط محفوظتان.

NEXT_STAGE=RUNWARE_MEDIA_QUEUE_AND_ELEVENLABS_TTS_V1

============================================================
RUNWARE IMAGE MODEL SELECTION AND LOCK V1 — 2026-08-05
============================================================

✓ Seedream 5.0 Pro هو نموذج الصور الرئيسي.
✓ Nano Banana 2 هو نموذج البشر المعقدين والثبات والتحرير المرجعي.
✓ FLUX.2 Pro مستبعد من الإنتاج الطبيعي.
✓ لا طلبات مدفوعة أثناء النشر أو الاختبار.

NEXT_STAGE=RUNWARE_MEDIA_QUEUE_AND_ELEVENLABS_TTS_V1

============================================================
LOCAL PROFESSIONAL GRAPHICS ENGINE V1 — 2026-08-05
============================================================

تم اعتماد وبناء أساس محرك الجرافيك المحلي الاحترافي:

✓ PySide6 للتحكم والتحقق والإيصالات.
✓ Qt Quick/QML للحركة والطبقات والشفافية.
✓ SVG وQML Canvas للخرائط والمسارات والعلاقات.
✓ FFmpeg لتحويل الإطارات إلى H.264 MP4.
✓ ستة قوالب: خط زمني، خريطة، شجرة علاقات، مصدر، مقارنة، مكان وزمان.
✓ حركة حتمية عبر frameProgress لكل إطار.
✓ دقة 1920×1080 ومعدل 30 إطارًا في الثانية.
✓ دعم العربية RTL وربط الخط من النظام دون تضمين ملفات خطوط.
✓ ربط كل جرافيك بمعرفات المصادر.
✓ الموسيقى ممنوعة.
✓ تكلفة API المحلية صفر.
✓ لا طلبات مدفوعة أثناء النشر أو الاختبار.

NEXT_STAGE=GRAPHICS_STORYBOARD_INTEGRATION_AND_MEDIA_QUEUE_V1

============================================================
GRAPHICS STORYBOARD INTEGRATION AND MEDIA QUEUE V1 — 2026-08-05
============================================================

✓ ست مواصفات جرافيك مرتبطة بالمصادر.
✓ 44 صورة موزعة على Seedream وNano Banana.
✓ 20 فيديو Veo 3.1 Lite مدة كل منها 8 ثوانٍ.
✓ 6 جرافيك محلي بلا تكلفة API.
✓ طابور ElevenLabs لكل مقطع نصي.
✓ اختيار صوت ElevenLabs مطلوب قبل التنفيذ.
✓ احتياطي وقائي أقصى 17.60$ ضمن سقف 40$.
✓ كل محاولة مدفوعة تحتاج تفويضًا صريحًا.
✓ لا إعادة مدفوعة خفية.
✓ تحديث سجل المراحل ومخطط إعادة البناء الجزئي.
✓ لا طلبات مدفوعة أثناء النشر أو الاختبار.

NEXT_STAGE=DESKTOP_MEDIA_EXECUTION_AND_ELEVENLABS_VOICE_SELECTION_V1

============================================================
ELEVENLABS FOUR PERFORMER CASTING LOCK V1 — 2026-08-05
============================================================

✓ تثبيت أربعة مؤدين مختارين مسبقًا.
✓ الأساسي: XdoLPWNt7ytn6BtU4FBf.
✓ ثلاثة احتياطيين/مؤدين إضافيين.
✓ النموذج: eleven_multilingual_v2.
✓ stability=0.55.
✓ similarity_boost=0.75.
✓ style=0.15.
✓ use_speaker_boost=true.
✓ الأساسي هو الراوي الافتراضي.
✓ استخدام أكثر من مؤدٍ حسب السيناريو والستوريبورد.
✓ ثبات صوت الشخصية عبر الحلقة.
✓ إزالة بوابة اختيار صوت جديدة.
✓ كل محاولة مدفوعة تحتاج تفويضًا صريحًا.
✓ لا إعادة مدفوعة خفية.
✓ لا طلبات مدفوعة أثناء النشر أو الاختبار.

NEXT_STAGE=DESKTOP_MEDIA_EXECUTION_V1
============================================================
DESKTOP MEDIA EXECUTION V1 — 2026-08-05
============================================================

✓ واجهة مستقلة لتنفيذ طابور الوسائط.
✓ تنفيذ صورة أو فيديو أو TTS محدد فقط.
✓ تفويض صريح لكل محاولة مدفوعة.
✓ قفل حصري قبل الاتصال بالشبكة.
✓ Runware يستخدم UUID v4 حقيقيًا.
✓ استعادة Runware عبر getResponse بنفس taskUUID دون إعادة إرسال.
✓ منع إعادة إرسال ElevenLabs تلقائيًا عند غموض نتيجة الشبكة.
✓ رندر الجرافيك المحلي منفردًا أو دفعة محلية بلا تكلفة API.
✓ تنزيل الملفات وحساب SHA-256 وتسجيل الإيصالات.
✓ تحديث الطابور والتكلفة وحالة المنسق.
✓ الانتقال إلى STRUCTURAL_MONTAGE_V1 بعد اكتمال جميع الأصول.
✓ لا طلبات مدفوعة أثناء النشر أو الاختبار.

NEXT_STAGE=STRUCTURAL_MONTAGE_V1_AFTER_MEDIA_ASSETS_COMPLETE

============================================================
SFX AND AUDIO MIX V1 — 2026-08-05
============================================================

تم تنفيذ الحزمة البرمجية الأولى من الحزم الأربع النهائية:

✓ بناء خط زمني صوتي من مدد الستوريبورد ومقاطع النص.
✓ وضع أداءات ElevenLabs على الخط الزمني مع ثبات المؤدين.
✓ قراءة sfx_cues_ar من كل لقطة.
✓ استخدام مكتبة محلية مرخصة عند توفرها.
✓ إنشاء مؤثرات محلية حتمية عبر FFmpeg عند غياب الأصل المحلي.
✓ تسجيل الصمت المصمم للقطات الخالية من المؤثرات.
✓ إنشاء Narration Stem مستقل.
✓ إنشاء SFX Stem مستقل.
✓ خفض المؤثرات تلقائيًا تحت الكلام عبر Side-chain Compression.
✓ ماستر نهائي -16 LUFS وTrue Peak -1.5 dBTP.
✓ إخراج WAV 24-bit/48kHz وM4A 192kbps.
✓ منع الموسيقى والأغاني والـMusical Score والألحان.
✓ تكلفة API للمؤثرات والمكساج المحلي = 0.00$.
✓ تشغيل آلي بعد اكتمال جميع أصول الوسائط.
✓ تحديث سجل المراحل ومخطط إعادة البناء الجزئي.
✓ لا طلبات مدفوعة أثناء النشر أو الاختبار.

NEXT_STAGE=STRUCTURAL_MONTAGE_AND_FINAL_RENDER_V1

============================================================
STRUCTURAL MONTAGE AND FINAL RENDER V1 — 2026-08-05
============================================================

تم تنفيذ الحزمة البرمجية الثانية من الحزم الأربع النهائية:

✓ تركيب 70 لقطة وفق ترتيب الستوريبورد ومددها الدقيقة.
✓ 44 صورة متحركة بتركيب خلفية ضبابية وطبقة أمامية نظيفة.
✓ ثمانية أنماط حركة حتمية للصور ومنع العرض المسطح.
✓ 20 فيديو مولد مع إزالة صوت المصدر بالكامل.
✓ تمديد آخر إطار فقط عندما تزيد مدة المونتاج عن مدة الفيديو المولد.
✓ دمج 6 عناصر جرافيك محلية مع حفظ تصميمها اللوني.
✓ قطع مباشر داخل التسلسل وFade قصير عند حدود التسلسلات.
✓ توحيد كل اللقطات إلى H.264 1920×1080 30fps yuv420p.
✓ دمج ماستر التعليق والمؤثرات وحده بوصفه مصدر الصوت النهائي.
✓ إخراج AAC 192kbps / 48kHz / Stereo.
✓ استئناف جزئي لكل لقطة عبر Receipt وSHA-256 وRender Fingerprint.
✓ عدم إعادة رندر اللقطات الصحيحة غير المتغيرة.
✓ فحص مساحة القرص قبل بدء الرندر الكامل.
✓ إخراج episode-master-v1.mp4 الجاهز للفحص الآلي.
✓ الموسيقى ممنوعة وصوت جميع المصادر المرئية منزوع.
✓ تكلفة API للمونتاج والإخراج المحلي = 0.00$.
✓ لا طلبات مدفوعة أثناء النشر أو الاختبار.

NEXT_STAGE=AUTOMATIC_QA_AND_PARTIAL_REPAIR_V1

============================================================
AUTOMATIC QA AND PARTIAL REPAIR V1 — 2026-08-05
============================================================

تم تنفيذ الحزمة البرمجية الثالثة من الحزم الأربع النهائية:

✓ فحص تقني حتمي لجميع اللقطات السبعين.
✓ التحقق من الإيصالات وSHA-256 ومصادر اللقطات.
✓ التحقق من H.264 1920×1080 30fps yuv420p.
✓ التحقق من AAC 48kHz Stereo ومعدل البت.
✓ كشف فترات السواد غير المخططة.
✓ كشف التجمد مع استثناء تمديد آخر إطار المخطط.
✓ كشف الصمت الطويل وقياس -16 LUFS وTrue Peak.
✓ إصلاح لقطة محلية محددة فقط عند فساد الرندر أو الإيصال.
✓ إعادة mux نهائي فقط عند عيب الحاوية أو الصوت المقفل.
✓ إعادة استخدام جميع اللقطات الصحيحة عبر الإيصالات.
✓ حد أقصى مروران للإصلاح المحلي.
✓ منع إعادة توليد الحلقة كاملة لعيب محلي.
✓ منع أي إعادة مدفوعة تلقائية.
✓ إيقاف السلسلة وتحديد اللقطة/مرحلة الصوت عند عيب مصدري.
✓ الانتقال إلى المراجعة البشرية النهائية بعد النجاح.
✓ الموسيقى ممنوعة.
✓ تكلفة API المحلية صفر.
✓ لا طلبات مدفوعة أثناء النشر أو الاختبار.

NEXT_STAGE=HUMAN_FINAL_REVIEW_AND_PUBLISHING_V1

============================================================
FINAL REVIEW AND PUBLISH PACKAGE V1 — 2026-08-05
============================================================

تم تنفيذ الحزمة البرمجية الرابعة والأخيرة من SIRAJ Production V1:

✓ بوابة مراجعة بشرية نهائية مستقلة بعد نجاح QA.
✓ سبعة تأكيدات إلزامية قبل اعتماد الحلقة.
✓ إعادة التحقق من SHA-256 لتقرير QA والفيديو النهائي والإيصال.
✓ قراران صريحان فقط: اعتماد أو طلب إصلاح محدد.
✓ طلب إصلاح منظم بالفئة ومعرفات اللقطات والملاحظات.
✓ إلزام إعادة QA بعد تغيير بصري أو صوتي أو في المحتوى.
✓ السماح بتعديل metadata فقط دون إعادة رندر أو QA.
✓ بناء حزمة نشر محلية تحتوي العنوان والوصف والوسوم والـchecksums.
✓ إنشاء أرشيف metadata صغير دون تكرار ملف الفيديو الكبير.
✓ تثبيت الفيديو المرجعي النهائي وبصمته داخل manifest.
✓ تحديث سجل المراحل ومخطط الاعتماد إلى READY_TO_PUBLISH.
✓ رفع YouTube يدوي فقط.
✓ منع OAuth وتخزين بيانات YouTube والرفع التلقائي.
✓ لا طلبات OpenAI أو Runware أو ElevenLabs أو YouTube أثناء النشر والاختبار.
✓ الموسيقى ممنوعة.
✓ تكلفة API المحلية صفر.

NEXT_STAGE=SIRAJ_PRODUCTION_V1_COMPLETE_READY_FOR_END_TO_END_RUN

============================================================
SIRAJ DESKTOP COMPLETE WORKSPACE AND RESUME V1 — 2026-08-05
============================================================

تم تنفيذ حزمة إكمال واجهة سراج ومسار استكمال الحلقة:

✓ إضافة تمرير رأسي كامل داخل نافذة الإنتاج.
✓ إضافة زر استكمال دائم وموجّه حسب المرحلة الحالية.
✓ فتح وحدة الإنتاج لكل حلقة غير مكتملة بدل فتح المجلد فقط.
✓ تفعيل صفحات المشاريع والحلقات والستوريبورد والحزم البصرية.
✓ تفعيل صفحات الفيديو والاعتمادات والتقارير والإعدادات.
✓ اكتشاف ملف deliverables/episode-master-v1.mp4.
✓ اكتشاف publishing/publish-package-v1.
✓ الحفاظ على بوابة اعتماد النطاق والمراجعة النهائية.
✓ إبقاء تأكيد الإنفاق المدفوع إلزاميًا.
✓ إبقاء رفع YouTube يدويًا.

NEXT_STAGE=END_TO_END_ACCEPTANCE_RUN_WITH_PUBLISH_ASSET_COMPLETION

============================================================
SIRAJ END-TO-END PRODUCTION AND YOUTUBE HANDOFF V1 — 2026-08-05
============================================================

تم إكمال خط الإنتاج التشغيلي من اختيار الموضوع إلى مجلد رفع YouTube:

✓ بوابة اعتماد موضوع واحدة قبل بدء البحث.
✓ تشغيل البحث والنص والستوريبورد تلقائيًا بعد الاعتماد.
✓ تفويض واحد بالحد الأقصى لجميع عناصر Runware وElevenLabs المتبقية.
✓ تنفيذ طابور الوسائط بالتتابع مع إعادة استخدام الإيصالات الصحيحة.
✓ استعادة مهام Runware المقفلة بنفس taskUUID دون إعادة إرسال.
✓ تشغيل المؤثرات والمكساج والمونتاج وQA تلقائيًا بعد اكتمال الوسائط.
✓ إبقاء المراجعة البشرية النهائية إلزامية.
✓ إنشاء فصول YouTube تلقائيًا من الستوريبورد.
✓ إنشاء SRT عربي من توقيتات TTS المقفلة داخل خطة الصوت.
✓ تجهيز إفصاح المحتوى المعاد بناؤه وإعداد الجمهور واللغة.
✓ تجهيز ورقة رفع واختصار YouTube Studio وchecksums.
✓ اعتماد Thumbnail ثابت بحسب الحقبة مع تأجيل تصميم القوالب.
✓ رفع YouTube والنشر يدويان، بلا OAuth أو YouTube API.

NEXT_STAGE=END_TO_END_ACCEPTANCE_RUN

============================================================
SIRAJ ACCEPTANCE RESUME BUTTON RECOVERY V1 — 2026-08-05
============================================================

✓ إصلاح زر استكمال الحلقة الصامت.
✓ استعادة الحالة العالقة من الملفات مع نسخة احتياطية.
✓ منع أي طلب مدفوع أثناء الاستعادة.

NEXT_STAGE=END_TO_END_ACCEPTANCE_RUN_RETRY

============================================================
SIRAJ EPISODE 001 PIPELINE ADOPTION V1 — 2026-08-12
============================================================

✓ تحديد السبب الحقيقي: الحلقة الأولى موجودة لكن current_episode_id غير مربوط بالمنسق الجديد.
✓ إنشاء جسر توافق من الماستر البشري المعتمد v2.1 إلى ملفات خط الإنتاج الحالي.
✓ حفظ جميع ملفات الحلقة القديمة من دون تعديل.
✓ بناء طابور 44 صورة و20 فيديو و6 عناصر جرافيك و14 مقطع TTS.
✓ عدم إرسال أي طلب إلى OpenAI أو Runware أو ElevenLabs أثناء الترحيل.
✓ إبقاء تفويض التكلفة والمراجعة البشرية النهائية إلزاميين.

NEXT_STAGE=AUTHORIZE_AND_EXECUTE_EPISODE_001_MEDIA_QUEUE

============================================================
SIRAJ RUNWARE SEEDREAM NEGATIVE PROMPT RECOVERY V1 — 2026-08-12
============================================================

✓ تحديد أول عطل فعلي في تشغيل الوسائط: Seedream 5 Pro يرفض negativePrompt.
✓ حذف الحقل غير المدعوم عند بناء الطلب وعند الإرسال كحماية مزدوجة.
✓ تصنيف HTTP 400 المحدد كرفض نهائي بدل محاولة polling غير صحيحة.
✓ أرشفة قفل IMG-SH-001 الفاشل وإعادته إلى الطابور لتفويض جديد صريح.
✓ عدم إرسال أي طلب إلى Runware أثناء الإصلاح.

NEXT_STAGE=REAUTHORIZE_AND_RESUME_EPISODE_001_MEDIA_QUEUE

============================================================
SIRAJ LOCAL GRAPHICS QML TEXT DIRECTION RECOVERY V1 — 2026-08-12
============================================================

✓ إصلاح خاصية layoutDirection غير المدعومة في قوالب Qt Quick الستة.
✓ إصلاح ربط y المكرر داخل قالب Comparison.
✓ تحميل القوالب الستة والتقاط إطار تجريبي من كل قالب.
✓ الحفاظ على جميع الوسائط المدفوعة المكتملة دون إعادة إرسال.
✓ إعادة عناصر الجرافيك المحلية غير المكتملة فقط.
✓ عدم إرسال أي طلب إلى Runware أو ElevenLabs أثناء الاستعادة.

NEXT_STAGE=RESUME_EPISODE_001_MEDIA_QUEUE_FROM_PENDING_LOCAL_GRAPHICS

============================================================
SIRAJ LOCAL GRAPHICS SUBPROCESS ISOLATION V1 — 2026-08-12
============================================================

✓ تحديد سبب تجمد الواجهة: إنشاء QQuickView من QThread مع QGuiApplication الخاصة بالواجهة.
✓ نقل كل رندر جرافيك محلي إلى عملية Python مستقلة تعمل بوضع offscreen.
✓ إبقاء خيط واجهة Qt حرًا لاستقبال الأحداث وتحديث شريط التقدم.
✓ الحفاظ على جميع الوسائط والإيصالات المكتملة دون إعادة إنتاج.
✓ عدم إرسال أي طلب مدفوع أثناء الإصلاح أو الاستعادة.

NEXT_STAGE=RESUME_EPISODE_001_MEDIA_QUEUE_WITH_RESPONSIVE_DESKTOP

============================================================
SIRAJ ELEVENLABS KEY VALIDATION AND RECOVERY V1 — 2026-08-12
============================================================

✓ منع حفظ أو استخدام مفتاح ElevenLabs لا يبدأ بـ sk_.
✓ التحقق من المفتاح قبل إنشاء قفل المحاولة وقبل أي اتصال شبكي.
✓ تصنيف invalid_api_key_prefix كرفض مصادقة نهائي غير مدفوع.
✓ أرشفة قفل TTS المرفوض وإعادة العنصر وحده إلى تفويض صريح جديد.
✓ الحفاظ على جميع الوسائط والإيصالات المكتملة وعدم إعادة أي عنصر مدفوع.
✓ عدم إرسال أي طلب إلى ElevenLabs أثناء الاستعادة.

NEXT_STAGE=CONFIGURE_VALID_ELEVENLABS_KEY_AND_RESUME_EPISODE_001

============================================================
SIRAJ MONTAGE PIXEL FORMAT NORMALIZATION AND RECOVERY V1 — 2026-08-12
============================================================

✓ تثبيت إخراج المونتاج على H.264 High / yuv420p / BT.709 limited.
✓ فحص Pixel Format بعد كل لقطة وإجراء تطبيع محلي عند الحاجة.
✓ أرشفة ملف rendering غير المتوافق واستئناف المونتاج من أول لقطة ناقصة.
✓ الحفاظ على جميع الوسائط المدفوعة والإيصالات واللقطات المكتملة.
✓ عدم إرسال أي طلب إلى Runware أو ElevenLabs أثناء الإصلاح.

NEXT_STAGE=RESUME_EPISODE_001_STRUCTURAL_MONTAGE

========================================================
SERIES PRODUCTION QUALITY V2 — 2026-08-12
========================================================

Status:
IMPLEMENTED_AND_TESTED

Scope:

- اعتماد سياسة إنتاج موحدة على مستوى سلسلة سراج.
- جعل إنتاج الوسائط Video-first وقائمًا على الجودة والتكلفة.
- ميزانية الفيديو المولد المستهدفة: 30 USD للحلقة.
- الحد الأعلى المطلق للفيديو المولد: 35 USD للحلقة.
- متوسط السلسلة المستهدف: 30 USD عبر نافذة من خمس حلقات.
- إلغاء الهدف التحريري الثابت لعدد ثواني الفيديو؛ الثواني ناتج عن الميزانية والجودة.
- إضافة تخطيط مالي ديناميكي لاختيار أفضل مزيج وسائط.
- فرض التشكيل الكامل لنص TTS مع مراجعة لغوية وبشرية.
- إضافة كتل أداء صوتي وتوقفات وسرعة سرد وثائقية مدروسة.
- إضافة قواعد استمرارية العالم والموقع والمشاهد الأخروية الرمزية.
- منع العرض الأرضي الافتراضي للعالم غير المشاهد.
- منع المونتاج المسطح للصور والتكبير البسيط والتجميد الطويل.
- حصر تمديد آخر إطار في 1.25 ثانية كحد أقصى.
- إضافة بوابة جودة نهائية للصوت والسواد والتجمد والعالم والميزانية.
- إنشاء ترحيل V2 لحلقة episode-001-adam مع اشتراط إعادة التخطيط والمراجعة البشرية.

Branch:
feature/series-production-quality-v2

Validation:

- Python compilation: PASS
- V2 focused tests: PASS
- Episode-001 migration: PASS
- Paid generation is not authorized by this change.

========================================================
ADAM VISUAL REPLAN AND COMPACT AUDIT V2 — 2026-08-12
========================================================

Status:
IMPLEMENTED_AND_TESTED

Scope:

- إصلاح ربط مدقق V2 بحيث يفضّل storyboard-and-media-plan-v2.
- منع إعادة كتابة خطة V2 من خطة V1 في كل تدقيق.
- دمج scene_domain وcharacter_location وحقول العالم في الستوريبورد.
- تحويل لقطات الحركة والتحول إلى GENERATED_VIDEO.
- توزيع الفيديو وفق هدف 30 USD وحد أعلى 35 USD.
- استخدام التكلفة المرصودة 5.3 USD لكل 160 ثانية كمرجع تخطيطي.
- تحويل الصور المتبقية إلى DYNAMIC_STILL_SEQUENCE متعددة اللوحات.
- منع أي لوحة ثابتة ديناميكية تتجاوز سبع ثوان.
- اختصار ناتج الطرفية وحفظ التفاصيل الكاملة في JSON.
- لم يتم السماح بأي تنفيذ مدفوع.

NEXT_STAGE=ARABIC_PERFORMANCE_SCRIPT_V2_AND_HUMAN_VISUAL_REVIEW

========================================================
ADAM FINAL MOTION GATE RESOLUTION V2 — 2026-08-12
========================================================

Status:
IMPLEMENTED_AND_TESTED

Scope:

- حل بوابة الحركة المتبقية تكراريًا من نطاقات تقرير V2 الفعلية.
- عدم خفض أي لقطة يعتبرها مدقق الحركة لقطة تحول أو حركة سردية.
- السماح باستخدام هامش 30–35 USD عند الحاجة بدل تخريب الجودة للالتزام الصارم بـ30 USD.
- استثناء الرسومات المصممة والوثائق والخرائط من شرط الفيديو المولد.
- تنظيف أي وصف أرضي متبقٍ داخل العالم العلوي الرمزي.
- قبول ARABIC_PERFORMANCE_SCRIPT_INVALID فقط إلى حين التشكيل والمراجعة البشرية.
- عدم إرسال أي طلب فيديو أو صوت مدفوع.

NEXT_STAGE=UPLOAD_ARABIC_PERFORMANCE_SOURCE_FOR_FULL_DIACRITIZATION

========================================================
ADAM APPROVED ARABIC PERFORMANCE V2 — 2026-08-12
========================================================

Status:
HUMAN_APPROVED_AND_AUDIO_GATE_PASS

Scope:

- إصلاح دالة قياس التشكيل بعد فشل توليد سابق.
- تثبيت النص العربي المشكول الذي راجعه المستخدم واعتمده.
- تعبئة 43 كتلة أداء ضمن 14 تسلسلًا.
- إنشاء episode-script-v2.json وإيصال الموافقة البشرية.
- تشغيل بوابة الجودة واختبارات V2 المستهدفة.
- عدم إرسال النص إلى TTS وعدم تنفيذ أي طلب مدفوع.

NEXT_STAGE=TTS_PREFLIGHT_AND_SHORT_SAMPLE_GENERATION

========================================================
ADAM TTS PREFLIGHT TEST FIXTURES V2 — 2026-08-12
========================================================

Status:
OFFLINE_PREFLIGHT_PASS

Scope:

- تحديث نصوص اختبارات ElevenLabs القديمة إلى نصوص عربية مشكلة.
- الحفاظ على شرط التشكيل الصارم في كود الإنتاج دون تخفيفه.
- إعادة تشغيل TTS preflight دون اتصال بالشبكة.
- التحقق من 43 كتلة أداء ومن اختيار الراوي الأساسي.
- منع أي طلب مزود أو تنفيذ مدفوع.

NEXT_STAGE=EXPLICIT_SAMPLE_AUTHORIZATION_OR_CREDENTIAL_CONFIGURATION

========================================================
ADAM STALE TTS LOCK AUDIT V2 — 2026-08-12
========================================================

Status:
OFFLINE_LOCK_AUDIT_COMPLETE

Scope:

- فحص أقفال ElevenLabs القديمة دون اتصال بالشبكة.
- أرشفة أقفال رفض المفتاح غير الصالح فقط.
- ترك الأقفال غير النهائية دون حذف تلقائي.
- إعادة تشغيل TTS preflight بعد الاسترداد الآمن.
- منع أي طلب مزود أو تنفيذ مدفوع.

NEXT_STAGE=EXPLICIT_SAMPLE_AUTHORIZATION_OR_MANUAL_LOCK_REVIEW

========================================================
ADAM AUTHORIZED TTS SAMPLE V2 — 2026-08-12
========================================================

Status:
ONE_SAMPLE_GENERATED_AWAITING_HUMAN_REVIEW

Scope:

- تسجيل التفويض الصريح لمحاولة ElevenLabs واحدة فقط.
- قفل النص والصوت والنموذج وحد 0.07 USD قبل الشبكة.
- منع إعادة المحاولة التلقائية أو الخفية.
- توليد عينة VB-001-01 وحفظ الإيصال والبصمة.
- إبقاء توليد الحلقة الكاملة غير مصرح به.

NEXT_STAGE=HUMAN_TTS_SAMPLE_REVIEW

========================================================
ARABIC ACTUAL STOP WAQF V2 — 2026-08-12
========================================================

Status:
BATCH_REVIEW_READY_NO_PAID_EXECUTION

Scope:

- تطبيق صورة الوقف على التوقفات الفعلية عالية الثقة.
- إبقاء الفواصل العارضة والتعداد في صورة الوصل.
- إنشاء مرشحَي المصدر والنص النهائي دون تغيير النص الأصلي.
- إنشاء تقرير تفصيلي قبل/بعد لكل كتلة أداء.
- إنشاء خطة أصوات محدثة لـ43 كتلة دون تفويض مدفوع.
- تسجيل قبول الصوت الأول مشروطًا بإصلاح الوقف.
- تجهيز طلب العينة الثانية دون تنفيذها.
- تجهيز بوابة جاهزية الحلقة الكاملة مع بقائها محظورة.
- تثبيت UTF-8 في مسار التنفيذ على Windows.
- تنفيذ صفر طلبات مزود وصفر طلبات مدفوعة.

NEXT_STAGE=HUMAN_WAQF_DIFF_REVIEW_AND_SECOND_SAMPLE_AUTHORIZATION

========================================================
ARABIC ACTUAL STOP WAQF V3 — 2026-08-12
========================================================

Status:
LINGUISTIC_HARDENING_REVIEW_READY_NO_PAID_EXECUTION

Scope:

- إصلاح مطابقة موضع الوقف اليدوي دون إسقاط همزة «الأمر».
- تثبيت موضع «مَنَعَهْ، وَلَا» بوصفه الوقف الوحيد المؤكد يدويًا.
- إبقاء سائر الفواصل في حالة الوصل افتراضيًا.
- إبقاء العينة الثانية والحلقة الكاملة غير مصرح بهما.
- تنفيذ صفر طلبات مزود وصفر طلبات مدفوعة.

NEXT_STAGE=HUMAN_WAQF_V3_REVIEW_AND_SECOND_SAMPLE_AUTHORIZATION

========================================================
ADAM AUTHORIZED WAQF V3 SAMPLE — 2026-08-12
========================================================

Status:
ONE_WAQF_V3_SAMPLE_GENERATED_AWAITING_HUMAN_REVIEW

Scope:

- تسجيل التفويض الصريح لمحاولة ElevenLabs واحدة فقط.
- قفل نص الوقف V3 والصوت والنموذج وسقف 0.07 USD.
- منع إعادة المحاولة التلقائية أو الخفية.
- توليد عينة VB-001-01 المصححة وحفظ الإيصال والبصمة.
- إبقاء توليد الحلقة الكاملة غير مصرح به.

NEXT_STAGE=HUMAN_WAQF_V3_SAMPLE_REVIEW

========================================================
SIRAJ SERIES PRODUCTION STANDARD V2 CAMERA AND BUDGET REPAIR — 2026-08-12
========================================================

Status:
READY_FOR_FULL_EPISODE_REBUILD_AUTHORIZATION

Resolved:

- Replaced the false camera-language coverage block with a real 70-shot cinematic camera plan.
- Added lens, scale, movement, composition, focus, screen direction and axis metadata to every shot.
- Added world, light, palette, material, silhouette and adjacent-shot continuity locks.
- Corrected planned generated-video spend discovery to 29.514375 USD.
- Re-ran the fail-closed director and technical gate successfully.
- Preserved the original storyboard and created a production-standard canonical storyboard.
- Performed zero provider requests and zero paid requests.

NEXT_STAGE=CONSOLIDATED_FULL_EPISODE_REBUILD_AUTHORIZATION

========================================================
LUNA CINEMATIC PROMPT DIRECTOR V2 — 2026-08-12
========================================================

Status:
AWAITING_CONSOLIDATED_LUNA_PROMPT_AND_FULL_EPISODE_AUTHORIZATION

Completed:

- Luna owns or supervises every provider-facing visual prompt.
- Prompt quality threshold is 95/100 with zero blocking flags.
- 70 Adam prompts are organized into 7 locked Luna batches.
- Provider execution is blocked without Luna certification.
- Legacy execution fixtures carry valid Luna certification.
- Uncertified execution is proven to stop before network and lock creation.
- Recovery reuses the locked certification without resubmission.
- Runtime enforcement was not weakened.
- No provider or paid request was sent during installation.

NEXT_STAGE=CONSOLIDATED_LUNA_PROMPT_AND_FULL_EPISODE_AUTHORIZATION

========================================================
CONSOLIDATED EPISODE PRODUCTION CONTROLLER V2 — 2026-08-12
========================================================

Status:
READY_FOR_ONE_CONSOLIDATED_DESKTOP_AUTHORIZATION

Completed:

- Repaired the V1 compatibility facade escaped module docstring.
- Repaired and regression-tested the montage 1.25-second extension cap.
- Installed the consolidated desktop production controller.
- Joined seven Luna prompt batches and the 43-block TTS plan.
- Added one desktop authorization and production button.
- Verified the Python source tree with AST and compileall.
- Installation performs zero provider and paid requests.

NEXT_STAGE=ONE_CONSOLIDATED_DESKTOP_AUTHORIZATION


========================================================
RUNTIME PRODUCTION V2 ENTRY REPAIR — 2026-08-12
========================================================

Status:
READY_FOR_ONE_CONSOLIDATED_DESKTOP_AUTHORIZATION

- Added non-enumerated V1 treatment aliases over canonical V2 counts.
- Canonical treatment total remains 70.
- ProductionConsole opens without ANIMATED_STILL_COMPOSITING KeyError.
- Dashboard prioritizes the V2 rebuild over the stale old master.
- Cleared Python bytecode caches.
- Zero provider and paid requests.

NEXT_STAGE=OPEN_SIRAJ_AND_AUTHORIZE_FROM_CONSOLIDATED_V2_BUTTON

========================================================
LUNA JSON INTEGRITY HARDENING — 2026-08-12
========================================================

Status:
READY_FOR_EXPLICIT_LUNA_RETRY_AUTHORIZATION

- First invalid response remains locked and is not retried.
- Raw provider responses will now be saved before parsing.
- Only message/output_text content is parsed as JSON.
- Reasoning effort is medium and output verbosity is low.
- Response incomplete/refusal/error states are classified.
- Strict schema and 95/100 quality gate remain unchanged.
- No provider or paid request was sent during this repair.

NEXT_STAGE=EXPLICIT_ONE_REQUEST_LUNA_RETRY_AUTHORIZATION

========================================================
EXPLICIT LUNA INVALID OUTPUT RETRY V2 — 2026-08-12
========================================================

Status:
READY_FOR_EXPLICIT_DESKTOP_RETRY_AUTHORIZATION

- The invalid Luna batch remains locked until confirmation.
- One replacement request has a supplemental 0.05 USD maximum.
- Effective protective maximum is 34.914375 USD.
- Failed lock is archived before the replacement request.
- Supplemental authorization is consumed before network activity.
- No second automatic or hidden retry is possible.
- Installation performs zero provider and paid requests.

NEXT_STAGE=CLICK_EXPLICIT_LUNA_RETRY_AND_CONTINUE

========================================================
LUNA SAFE TECHNICAL REPAIR V1 — 2026-08-12
========================================================

Status:
AUTOMATIC_BOUNDED_REPAIR_ENABLED

- Production automatically invokes Luna for eligible local technical failures.
- Passing repairs resume the same production chain without user interruption.
- Maximum 3 calls, 0.15 USD total, 5 files and 200 lines per repair.
- Every change is backed up, validated and rollback-capable.
- Provider ambiguity, paid retries, permissions and architectural changes stop for user action.
- Installation performs zero provider and paid requests.

NEXT_STAGE=OPEN_SIRAJ_AND_CONTINUE_CONSOLIDATED_PRODUCTION

========================================================
V2 STATE RESUME TTS FIXTURE FINALIZATION — 2026-08-12
========================================================

Status:
READY_TO_RESUME_CERTIFIED_V2_MEDIA_QUEUE

- Preserved the production TTS diacritic gate unchanged.
- Updated only the obsolete synthetic narration test fixture.
- Passed the focused state, queue, controller, repair, and end-to-end tests.
- Preserved the old QA state in a backup before the V2 state rebase.
- No provider or paid request was sent.

NEXT_STAGE=OPEN_SIRAJ_AND_CONTINUE_CONSOLIDATED_PRODUCTION

========================================================
WINDOWS SNAPSHOT PERMISSION RECOVERY ANCHORLESS V2 — 2026-08-12
========================================================

Status:
READY_TO_RESUME_CONSOLIDATED_PRODUCTION

- Replaced the brittle text-anchor installer with runtime overrides.
- Desktop snapshot access is retried and then deferred when Windows locks it.
- The V2 panel overlays pending snapshot updates.
- Authoritative plans, locks, receipts and budgets remain fail-closed.
- No provider or paid request was sent.

NEXT_STAGE=OPEN_SIRAJ_AND_CONTINUE_CONSOLIDATED_PRODUCTION

========================================================
NATIVE V2 FLOAT CONTRACT FINALIZATION — 2026-08-12
========================================================

Status:
PASS_FULL_PRODUCTION_PIPELINE_CERTIFIED

- Resolved the final IEEE-754 equality conflict between legacy tests.
- Full repository tests, compileall, Qt, FFmpeg and certification passed.
- Provider requests: 0.
- Paid provider requests: 0.

NEXT_STAGE=ONE_EXPLICIT_NATIVE_V2_EXECUTION_AUTHORIZATION

========================================================
VEO PAYLOAD AND PRODUCTION CONSOLE REPAIR — 2026-08-07
========================================================

Status:
PASS_VEO_PAYLOAD_AND_PRODUCTION_CONSOLE_REPAIRED

- Removed unsupported negativePrompt from all Veo requests.
- Preserved exclusions inside the certified positive provider prompt.
- Added a strict Veo parameter allowlist before provider submission.
- Recovered VID-SH-001-C01 without automatic resubmission.
- Reduced the production console to one contextual production action.
- Added functional vertical scrolling to the full production console.
- Full pytest, compileall, Qt and certification checks passed.
- Provider requests during repair: 0.
- Paid provider requests during repair: 0.

NEXT_STAGE=REOPEN_SIRAJ_AND_CLICK_CONTINUE_EPISODE_PRODUCTION

========================================================
VEO NETWORK-BOUNDARY FINALIZATION — 2026-08-07
========================================================

Status:
PASS_VEO_NETWORK_BOUNDARY_FINALIZED

- Corrected the resume installer detection bug that mistook the helper definition for an active call inside execute_runware_item.
- The Veo sanitizer now runs after Luna prompt application and before the Runware network lock/request.
- The regression test verifies call order through Python AST rather than fragile formatting-dependent text matching.
- The zero-cost failed queue item remains ready for explicit continuation.
- Full pytest, compileall and stable pipeline certification passed.
- Provider requests during repair: 0.
- Paid provider requests during repair: 0.

NEXT_STAGE=FULLY_CLOSE_AND_REOPEN_SIRAJ_THEN_CONTINUE_EPISODE

========================================================
ACTIVE PRODUCTION REFRESH FREEZE REPAIR — 2026-08-07
========================================================

Status:
PASS_ACTIVE_PRODUCTION_REFRESH_FREEZE_REPAIRED

- Manual full-state refresh is blocked while any production worker runs.
- Refresh, route-refresh and consolidated-plan-refresh buttons are disabled during active production and re-enabled automatically after completion.
- Progress labels continue to update from the worker thread.
- Idle refresh behavior is preserved.
- Full pytest and compileall passed.
- Provider requests during repair: 0.
- Paid provider requests during repair: 0.

NEXT_STAGE=REOPEN_SIRAJ_AND_RESUME_FROM_THE_EXISTING_LOCK_OR_NEXT_ITEM

========================================================
EPISODE 002 PRODUCTION QUALITY CHECKPOINT — 2026-08-12
========================================================

Current production-quality work:

- Episode 002 reached surgical visual repair preproduction V2.2.
- V2.2 remains under human review and is NOT approved for visual generation.
- Current narration is frozen as the episode duration authority.
- Legacy female visuals are excluded from production reuse.
- Graphics remain forbidden from the final episode.
- No paid visual generation is authorized by this checkpoint.
- Next engineering step: V2.3 surgical preproduction correction and human approval gate.

Safety state:

STORYBOARD_STATUS=AWAITING_HUMAN_APPROVAL
VISUAL_GENERATION_ALLOWED=FALSE
AUTOMATIC_PAID_RETRY=FALSE
AUTOMATIC_PAID_RESUBMISSION=FALSE

========================================================

========================================================
EPISODE 002 SURGICAL VISUAL REPAIR V2.3 — 2026-08-12
========================================================

Status:
PASS_AUTOMATED_V2_3_GATES_PENDING_HUMAN_TEMPORAL_AUDIT

Completed:

- Reduced V2.2 visual generation plan from 54 provider units / 362 provider seconds
  to 23 provider units / 176 provider seconds.
- Removed the generic support-generation explosion.
- Kept only event-bearing surgical diversity anchors.
- Fixed provider source-range capacity for consolidated generation units.
- Canonical provider prompt is VISUAL_PROVIDER_PROMPT only.
- Legacy COMPILED_PROVIDER_PROMPT is not consumable in V2.3 new shots.
- Corrected Adam/Hawwa eating staging: occlusion/edit coverage; no fruit-through-fabric.
- Corrected shared supplication.
- Earth clips begin already on Earth; no provider-generated paradise-to-earth morph.
- Musa core source-backed physical traits retained while authentic hair-texture variants remain non-canonicalized.
- Separate Adam/Hawwa Earth staging classified as non-authoritative TIER_5 permissible lower-tier staging; exact geography forbidden.
- Generated all-decoded-frame temporal contact sheets for every reused legacy video asset.
- Full temporal female review remains human-gated.
- No production network/provider/paid calls were made.
- No visual generation was performed.
- No montage was performed.

Safety:

STORYBOARD_STATUS=AWAITING_HUMAN_APPROVAL
APPROVED_STORYBOARD_SHA256=NULL
VISUAL_GENERATION_ALLOWED=FALSE
TEMPORAL_FEMALE_HUMAN_REVIEW_STATUS=PENDING
AUTOMATIC_PAID_RETRY=FALSE
AUTOMATIC_PAID_RESUBMISSION=FALSE

NEXT=HUMAN_STORYBOARD_V2_3_AND_TEMPORAL_FEMALE_AUDIT_REVIEW

========================================================

========================================================
EPISODE 002 FINAL EDITORIAL SURGICAL REBALANCE V2.4 - 2026-08-13
========================================================

Status:
PASS_AUTOMATED_V2_4_GATES_AWAITING_FINAL_HUMAN_STORYBOARD_APPROVAL

Preproduction result:

- Provider plan: 27 units / 208 generated seconds.
- Planned Veo 3.1 Lite 720p cost: USD 10.40.
- Hard planning cap: USD 12.00.
- Four new 8-second Adam-Musa continuity units cover the remaining debate window.
- The generic legacy tail after 479.583s is eliminated.
- From 511.583s to episode end, recap callbacks use already planned generated narrative material and create zero provider calls.
- Legacy reused timeline reduced below 50 percent.
- Legacy exact-range second uses reduced to 9 or fewer.
- Legacy female all-frame human review: PASS.
- Legacy female reuse count: 0.
- Word-level alignment is not claimed; beat-level plus human event/recap anchors remain subject to rendered sync review.
- No production network/provider/paid calls were made.
- No visual generation or montage was performed.

Safety:

STORYBOARD_STATUS=AWAITING_HUMAN_APPROVAL
APPROVED_STORYBOARD_SHA256=NULL
VISUAL_GENERATION_ALLOWED=FALSE
PAID_GENERATION_AUTHORIZATION_GRANTED=FALSE
AUTOMATIC_PAID_RETRY=FALSE
AUTOMATIC_PAID_RESUBMISSION=FALSE

NEXT=HUMAN_STORYBOARD_V2_4_FINAL_REVIEW

========================================================

========================================================
EPISODE 002 V2.4 PRODUCTION ARM FIX3 - 2026-08-13
========================================================

Status:
PASS_READY_FOR_EXPLICIT_DESKTOP_FIRST_ATTEMPT_START

Authority:
- Storyboard SHA256: a01f945615bbd18409745607b98fba87bba39c71ffa99bc2019cc0462c9faef8
- Provider-plan SHA256: 3ea9b8d751fd7f75433128e031c462e1837f633c4df99317660ebacf7234c152
- 27 Veo 3.1 Lite first-attempt units / 208 provider seconds.
- Planned cost USD 10.40; hard cap USD 12.00.

FIX3 certification:
- Exact baseline default full pytest: PASS_KNOWN_PREEXISTING_UNTRACKED_FIXTURE_DEPENDENCY.
- Hard V2.4 release tests: PASS.
- Legacy provider tests: PASS_GREEN_CURRENT.
- Post-change default full pytest: PASS_GREEN_CURRENT.
- No provider/paid generation occurred during recovery.
- Stage-level completion receipt is now readable after all 27 durable completions.
- Final render review package uses ALL decoded frames in 8x8 contact sheets, not 1-fps sampling.

Safety:
- First attempts only.
- Stop on first FAILED / UNKNOWN / unresolved.
- No automatic paid retry or resubmission.
- No montage or QA until human render-conformance review.
- Desktop click remains mandatory for first paid request.

NEXT=EXPLICIT_DESKTOP_V24_FIRST_ATTEMPT_START

========================================================

========================================================
EPISODE 002 V2.4 PRODUCTION ARM FIX5 - 2026-08-13
========================================================

Status:
PASS_READY_FOR_EXPLICIT_DESKTOP_FIRST_ATTEMPT_START

Authority:
- Storyboard SHA256: a01f945615bbd18409745607b98fba87bba39c71ffa99bc2019cc0462c9faef8
- Provider-plan SHA256: 3ea9b8d751fd7f75433128e031c462e1837f633c4df99317660ebacf7234c152
- 27 Veo 3.1 Lite first-attempt units / 208 provider seconds.
- Planned cost USD 10.40; hard cap USD 12.00.

FIX5 certification:
- Exact baseline default full pytest: PASS_KNOWN_PREEXISTING_UNTRACKED_FIXTURE_DEPENDENCY.
- Hard V2.4 release tests: PASS.
- Legacy provider tests: PASS_GREEN_CURRENT.
- Post-change default full pytest: PASS_GREEN_CURRENT.
- No provider/paid generation occurred during recovery.
- Stage-level completion receipt is now readable after all 27 durable completions.
- Final render review package uses ALL decoded frames in 8x8 contact sheets, not 1-fps sampling.

Safety:
- First attempts only.
- Stop on first FAILED / UNKNOWN / unresolved.
- No automatic paid retry or resubmission.
- No montage or QA until human render-conformance review.
- Desktop click remains mandatory for first paid request.

NEXT=EXPLICIT_DESKTOP_V24_FIRST_ATTEMPT_START

========================================================

========================================================
UNIFIED CONSTITUTION OFFLINE ENFORCEMENT E6/E7 V1 - 2026-08-13
========================================================

Status:
OFFLINE_ENFORCEMENT_PASS

Certification:
- E0 through E7: PASS.
- Canonical rules covered: 51/51.
- Critical/high unenforced rules: 0/0.
- Constitutional enforcement suite: 338 passed, 0 failed, 0 skipped.
- Relevant repository suite: 206 passed, 0 failed, 0 errors, 0 skipped.
- Full repository suite: 696 passed, 0 failed, 0 errors, 1 existing live-provider opt-in skip.
- Python compile-all and staged diff checks: PASS.
- Type checking: NOT_CONFIGURED.

Legacy recovery:
- Initial relevant run exposed 15 failures across stale historical alignment/provider fixtures.
- Preserved alignment review now requires immutable failure-ledger evidence bound to current authority artifact hashes.
- Provider-stage tests materialize verified historical append-only prefixes in isolated clones.
- Recovery maps request IDs to pending attempt IDs and still blocks any pending attempt without a durable provider operation ID.
- E7 uses independently generated SHA256-bound raw evidence and has no final-certificate self-reference.

Safety:
- Provider calls: 0.
- Paid calls: 0.
- Network production calls: 0.
- Retries/resubmissions: 0/0.
- Montage/production/publication executions: 0/0/0.
- Production authorization remains false.
- Production, Episode 002 production, provider execution, paid execution, montage, and publication remain NO_GO.

NEXT=WAIT_FOR_NEW_EXPLICIT_HUMAN_AUTHORIZATION

========================================================

========================================================
SIRAJ SHORTS DERIVATIVE ENGINE V1 - 2026-08-14
========================================================

Status:
SHORTS_DERIVATIVE_ENGINE_V1_PASS_FOR_OFFLINE_CERTIFICATION

Implementation:
- Added the constitutional, extractive Shorts Director pipeline from local episode ingestion through intelligence, candidate discovery, explainable scoring, portfolio selection, context repair, shot-by-shot vertical reframe, source-audio editing, immutable render plans, local fixture rendering, QA, and human review/export contracts.
- Added versioned SIRAJ_SHORTS_DERIVATIVE_PROFILE_V1 with no silent defaults, creator-strategy duration values, dynamic candidate/publication counts, external captions only, and no provider/network/paid/publication capability.
- Added an integration point in the existing Desktop application; no second GUI was created. Public title and thumbnail remain human-owned.
- Reused the unified constitution loader/enforcement and hash-bound provenance primitives. The unified constitution and core enforcement module were not modified.

Certification:
- Shorts unit/integration/adversarial/renderer suite: 28 passed, 0 failed.
- Constitutional enforcement suite: 338 passed, 0 failed.
- Constitutional adversarial/runtime/global regressions: 150 passed, 0 failed.
- Full repository suite: 724 passed, 0 failed, 1 existing live-provider opt-in skip.
- Python compileall and git diff checks: PASS.
- Desktop Shorts dock offscreen construction: PASS.
- Local renderer determinism, source immutability, exact plan binding, and hash-bound export: PASS.

Safety:
- Provider calls: 0.
- Paid calls: 0.
- Network production calls: 0.
- YouTube API calls: 0.
- Real episode short renders during certification: 0.
- New TTS/visual generations: 0/0.
- Music additions, automatic title/thumbnail generation, uploads, and publications: 0/0/0/0/0.
- OPEN-M03 remains deferred; uncalibrated face detection cannot grant final visual PASS.
- Real episode execution remains NO_GO pending explicit human authorization.

Authority:
- Unified constitution: SIRAJ_UNIFIED_PRODUCTION_CONSTITUTION 1.0.0.
- Constitution bundle SHA256: 77c451711eb1888664518c9fe89e176033fdf7612f4636e18c0e0ca4d3af4f54.
- Shorts profile: SIRAJ_SHORTS_DERIVATIVE_PROFILE_V1.
- Certification packet: reports/shorts-derivative-engine-v1/.

NEXT=USER_PROVIDES_SELECTED_EPISODE_FOR_FIRST_CONTROLLED_SHORTS_RUN

========================================================

========================================================
SIRAJ SHORTS DIRECT-USE ACTIVATION AND CANONICAL DESKTOP STORAGE - 2026-08-14
========================================================

Status:
SHORTS_ENGINE_READY_FOR_DIRECT_HUMAN_CONTROLLED_LOCAL_USE

Completed:

- Activated the existing Desktop Shorts surface through SOURCE, ANALYZE, CANDIDATES, PORTFOLIO, RENDER_PLANS, LOCAL_RENDERS, QA_REVIEW, and EXPORT stages.
- Added hash-bound, single-use Desktop authorization with live Qt runtime validation, explicit click, nonce, consumed state, and idempotency lock.
- Added source and metadata hash revalidation, stale-state invalidation, resumable workflow state, asynchronous QThread work, and cancellable local FFmpeg execution.
- Added canonical Desktop discovery and the stable SIRAJ Shorts library with Shorts, Captions, Manifests, and Reviews folders.
- Added atomic no-overwrite exports, ALREADY_EXPORTED handling, versioned -v2 outputs, manifest hash equality, moved-root detection, and filesystem index rebuild.
- Preserved provider, paid, network production, retry/resubmission, montage, new TTS, new visual generation, upload, auto-publication, title automation, and thumbnail automation as forbidden.
- Kept the unified constitution and core enforcement unchanged. Constitution bundle SHA256 remains 77c451711eb1888664518c9fe89e176033fdf7612f4636e18c0e0ca4d3af4f54.

Certification:

- Shorts/Desktop matrix: 67 passed.
- Canonical storage matrix: 23 passed.
- Full repository matrix: 753 passed, 1 skipped; the skip is live-provider opt-in only.
- Native smoke: REAL_NATIVE_EPISODE_SMOKE=NOT_AVAILABLE_NO_SAFE_INPUT because EP002 native admission blocks ambiguous metadata.
- Critical unresolved gaps: 0.
- High unresolved gaps: 0.
- Human final visual/constitutional certification remains mandatory.

Safety:

- Provider calls: 0.
- Paid calls: 0.
- Network production calls: 0.
- Retries/resubmissions: 0/0.
- Montage/YouTube/publication executions: 0/0/0.

Evidence:

- reports/shorts-derivative-engine-v1/SHORTS_ENGINE_REAL_USE_READINESS_CERTIFICATION_V1.json
- reports/shorts-derivative-engine-v1/SHORTS_REAL_USE_READINESS_GAP_AUDIT_V1.json
- reports/shorts-derivative-engine-v1/SHORTS_CONFLICT_MATRIX_V1.json
- reports/shorts-derivative-engine-v1/SHORTS_GAP_ENFORCEMENT_MATRIX_V1.json
- reports/shorts-derivative-engine-v1/SHORTS_DEPENDENCY_APPROVAL_INVALIDATION_MODEL_V1.json

NEXT=OPEN_SIRAJ_DESKTOP_AND_SELECT_AN_ADMITTED_SAFE_EPISODE_FOR_THE_FIRST_CONTROLLED_LOCAL_SHORTS_RUN

========================================================

========================================================
SIRAJ SHORTS CONVERSION AND BURNED CAPTIONS DIRECTOR V1 - 2026-08-14
========================================================

Status:
SHORTS_CONVERSION_DIRECTOR_AND_CAPTION_ENGINE_CERTIFIED_EP001_CAPTION_TIMING_BLOCKED_FAIL_CLOSED

Completed:

- Added the explicit Short-to-Longform Conversion Director with hook, retention, standalone value, open-loop, conversion, spoiler, payoff-overdisclosure, endpoint, provenance, and cumulative portfolio controls.
- Added the Shorts-only burned narration caption engine with narration-only text authority, trusted hash binding, explicit Short local timebase remapping, safe-area/placement gates, two-line limit, RTL/mixed-direction contracts, and no proportional timing guessing.
- Amended the unified constitution to version 1.1.0 with a scoped Shorts burned-narration-caption exception. Longform burned captions and on-screen subtitles remain forbidden and enforced.
- Rebound PR01 against constitution bundle SHA256 c82097a3de2dfa9c4b7a4b6d2c7c1b1f7fab909d25575724167e8ea7f4e3c7b8; M01/M02/M03 inputs were unchanged and historical UNKNOWN remains blocked.
- Added Shorts Desktop caption UX with default ON, technical-details-only disclosure, and an explicit no-caption-control Longform model.

Certification:
- Conversion/caption/UX integration matrix: 75 passed.
- Relevant Shorts/Desktop/legacy/storage/PR01/constitutional matrix: 368 passed.
- Full repository suite: 879 passed, 1 existing live-provider opt-in skip.
- Python compileall, git diff checks, secret scan, PR01 rebind, and visual fixture manifest: PASS.
- Representative 1080x1920 dark Arabic and bright mixed-direction synthetic frames were visually inspected; no production render or export was performed.
- EP001 source admission: PASS, auto-discovered trusted timing, 43 segments, final-video absolute timebase, source and final narration hashes bound, 229 analysis candidates.
- EP001 caption planning: CAPTION_TIMING_INSUFFICIENT. The historical evidence is coarse; no eligible 15-60 second candidate has sufficient trusted caption granularity. No ASR, proportional split, or invented timing was used.

Safety:
- Provider calls: 0.
- Paid calls: 0.
- Network production calls: 0.
- Retries/resubmissions: 0/0.
- Production renders/montage/publication/YouTube API: 0/0/0/0/0.
- New TTS/narration/visual generation: 0/0/0.
- Production and paid authorization remain false.

Evidence:
- reports/shorts-conversion-captions-v1/
- reports/pr01-production-readiness/SIRAJ_PRODUCTION_READINESS_PROFILE_V1.json
- tests/fixtures/shorts_caption_visual_fixtures_v1.json

NEXT=SUPPLY_OR_SELECT_TRUSTED_WORD_OR_PHRASE_TIMING_FOR_EP001_THEN_RERUN_CAPTION_PLANNING

========================================================

## SIRAJ_CONSTITUTION_V1_2_SIX_FIXES_IMPLEMENTATION

- Date: 2026-08-16
- Constitution: `SIRAJ_UNIFIED_PRODUCTION_CONSTITUTION`
- Version: `1.2.0`
- Bundle ID: `SIRAJ-CONSTITUTION-1.2.0-20260815`
- Bundle manifest SHA256: `b390d8a61382ece4e8daeb5993fc89bb013a9b74cd8d06b2fb6e41f0b7d001d5`
- Scope: exactly `C2 + C3 + C6 + C8 + H3 + H4`
- C2: no blanket authorization; existing machine-enforced paid/cost/hash-bound authorization stack retained.
- C3: global rule is generic for any historical `SUBMISSION_UNKNOWN`; no EP002-specific attempt identity remains in the global rule or validator.
- C6: burned narration captions allowed for Shorts only; Long-form remains forbidden.
- C8: exactly one active machine rule source under `config/constitution`; 1.1.0 preserved in `config/constitution-archive`.
- H3: material demonstrable anachronism is hard fail; minor uncertain detail is weighted review.
- H4: pilot is risk-conditional and uses existing bound validators.
- `C7`: unchanged.
- Provider calls: `0`
- Paid calls: `0`
- Network production calls: `0`
- Publication: `0`

## SIRAJ_CONSTITUTION_1_2_GLOBAL_ENFORCEMENT_COVERAGE_RECERTIFICATION_V1

- Date: 2026-08-16
- Constitution: `SIRAJ_UNIFIED_PRODUCTION_CONSTITUTION`
- Version: `1.2.0`
- Bundle manifest SHA256: `b390d8a61382ece4e8daeb5993fc89bb013a9b74cd8d06b2fb6e41f0b7d001d5`
- Starting commit: `30cac53e91f22a2bc9896b2c287874c44e421b3e`
- Rule count: `51`
- Covered rules: `51`
- Uncovered rules: `0`
- Critical rules unenforced: `0`
- High rules unenforced: `0`
- Validator implementations complete: `true`
- Constitution test files executed: `9`
- Constitution tests: `PASS`
- Runtime enforcement coverage: `PASS`
- Production authorized globally: `false`
- Provider calls: `0`
- Paid calls: `0`
- Network production calls: `0`
- Publication: `0`
- Coverage manifest SHA256: `81f34709967d9985fe6622edc959668a795c5fdd6d497e70a133ccc658a77e2f`
- Next stage: `PR01_CONSTITUTION_1_2_REBINDING_AND_RESUME`

## SIRAJ_PR01_CONSTITUTION_1_2_REBINDING_AND_RESUME_V1

- Date: 2026-08-16
- Status: `PASS_PR01_CONSTITUTION_1_2_REBINDING_AND_RESUME`
- Constitution version: `1.2.0`
- Constitution bundle SHA256: `b390d8a61382ece4e8daeb5993fc89bb013a9b74cd8d06b2fb6e41f0b7d001d5`
- Previous constitution version: `1.1.0`
- Previous constitution bundle SHA256: `c82097a3de2dfa9c4b7a4b6d2c7c1b1f7fab909d25575724167e8ea7f4e3c7b8`
- Global enforcement coverage commit: `9e4e481c3dbc3dae1d4f5ea955b95bf241999e1d`
- Global enforcement coverage manifest SHA256: `81f34709967d9985fe6622edc959668a795c5fdd6d497e70a133ccc658a77e2f`
- Historical M01/M02/M03: `COMPATIBILITY_REVALIDATED`, rebuild not required
- Historical PR01 certification: historical evidence only; not required to contain Constitution 1.2 identity
- R27 units: `27`, all remain `PENDING_HUMAN_REVIEW / NOT_STARTED`
- R27 live asset hashes: `27/27 MATCH`
- Montage allowed: `false`
- QA allowed: `false`
- Provider retry allowed: `false`
- Global production authorization: `false`
- Paid execution authorization: `false`
- Provider calls: `0`
- Paid calls: `0`
- Network production calls: `0`
- Publication: `0`
- Resume certification SHA256: `e43a53f70f74ee7cbb1bfc2aa3b71e545a04eb6f2c4c6bec739176431d04f3b2`
- Next stage: `EP002_AUDIO_FREEZE`

## SIRAJ_EP002_AUDIO_FREEZE_V1

- Date: 2026-08-16
- Status: `PASS_EP002_AUDIO_FREEZE`
- Episode: `episode-002-adam-temptation-fall-repentance`
- Constitution version: `1.2.0`
- Constitution bundle SHA256: `b390d8a61382ece4e8daeb5993fc89bb013a9b74cd8d06b2fb6e41f0b7d001d5`
- PR01 resume commit: `8376ba5b8c26b20e34782a158609f8f03b2340c0`
- Frozen narration master: `projects/episode-002-adam-temptation-fall-repentance/orchestration/montage-v6-2-1/narration-master-v6-2-1.wav`
- Frozen narration master SHA256: `1ac040b13db40b2aef87625bcd476d905a3157833d6ffb62de1e2ef0f2ec97a4`
- Frozen narration duration seconds: `623.5111041666667`
- Timeline declared duration seconds: `623.584`
- Duration difference retained as evidence seconds: `0.0728958333332912`
- Audio freeze manifest SHA256: `31c55d50726ac8a16d9b9f72986ed2343254829827b552c9cbdb7957aac424ac`
- Narration bytes modified by freeze: `false`
- Timeline/storyboard timing/prompt timing/cost/pilot/paid/montage/final certification: `REVALIDATION_REQUIRED`
- R27 recertification started: `false`
- Provider calls: `0`
- Network production calls: `0`
- Paid calls: `0`
- Publication: `0`
- Next stage: `EP002_R27_RECERTIFICATION`
