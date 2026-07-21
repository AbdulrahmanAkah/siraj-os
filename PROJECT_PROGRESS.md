# SIRAJ OS
## Master Development Roadmap

<!-- SIRAJ_AUTO_PROGRESS_BEGIN -->
## الحالة التنفيذية الآلية للمشروع

**آخر مزامنة:** 2026-07-21T13:39:57.111050+00:00

### الهدف المرجعي

- **الهدف قصير المدى:** إنتاج أول حلقة وثائقية قابلة للنشر من المصدر إلى ملف MP4، ثم تحويل المسار إلى قالب إنتاج متكرر.
- **الهدف طويل المدى:** بناء مصنع محتوى معرفي يعيد استخدام المعرفة الموثقة في الوثائقيات والمقاطع القصيرة والمقالات والبودكاست والدورات.
- **الهدف الأعلى:** إنشاء خط إنتاج آلي وموثّق لفيديوهات التاريخ وفق المصادر الإسلامية، من خلق آدم عليه السلام إلى قيام الساعة.
- **دور Gold-20:** Gold-20 بوابة معايرة وجودة محدودة داخل مسار المعرفة، وليس الهدف الرئيسي للمشروع.

### قاعدة تحديث المشروع

يجب تحديث PROJECT_PROGRESS.md وسجل milestones آليًا بعد كل خطوة تنفيذية كبيرة، دون انتظار طلب المستخدم.

### أحدث خطوة كبيرة

- **المعرّف:** `2026-07-21-episode-render-manifest-v2`
- **العنوان:** إنشاء Episode Render Manifest v2 ومخطط المشاهد الموقّتة
- **الحالة:** `COMPLETED`
- **الملخص:** تم تثبيت المرجع الاستراتيجي للوصول إلى أعلى مستوى إنتاجي داخل PROJECT_PROGRESS.md، وإنشاء خطة Production Excellence، وعقد Episode Render Manifest v2 الذي يدعم توقيتًا مستقلًا لكل مشهد، انتقالات وحركات لكل مشهد، طبقات صوت متعددة، ترجمة جانبية أو محروقة، وربط المشاهد بالادعاءات والمصادر والسياسة البصرية.
- **الخطوة التالية:** تطوير Render Adapter v2 ليستهلك توقيت المشاهد وطبقات الصوت والترجمة من Episode Render Manifest v2، ثم إنتاج فيديو فعلي مختلف التوقيت.

### أحدث Milestones

- `COMPLETED` — إنشاء Episode Render Manifest v2 ومخطط المشاهد الموقّتة (`2026-07-21-episode-render-manifest-v2`)
- `COMPLETED` — إنتاج فيديو ثانٍ من Render Manifest عام (`2026-07-21-render-adapter-v1-replay`)
- `COMPLETED` — تنظيف حالة Source Control وتصنيف ملفات العمل (`2026-07-21-repository-source-control-cleanup`)
- `COMPLETED` — تشغيل تدقيق جاهزية خط الوثائقي (`fast-track-readiness-audit-v1`)
- `COMPLETED` — تدقيق مسار إنتاج quality-gate-v4.mp4 (`2026-07-21-quality-gate-v4-lineage-audit`)
- `COMPLETED` — مزامنة حالة الوسائط مع تدقيق Fast Track (`2026-07-21-fast-track-media-state-synchronized`)
- `COMPLETED` — تثبيت التحديث الآلي لسجل تقدم المشروع (`2026-07-21-progress-automation-installed`)
- `COMPLETED_WITH_LIMITATIONS` — إثبات عمل خط إنتاج الفيديو مبدئيًا (`2026-07-21-media-video-prototype`)

السجل المنظم:

`docs/execution/project-milestones.json`
<!-- SIRAJ_AUTO_PROGRESS_END -->

> FAST-TRACK EXECUTION SOURCE OF TRUTH: `docs/execution/FAST_TRACK_EXECUTION_MAP.md`
>
> Immediate deliverable: first publishable documentary, Episode 001 - The Creation of Adam.
>
> Gold-20 is a bounded knowledge-quality gate, not the program objective.

آخر تحديث:
2026-07-08

========================================================
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
Voice ................... PROTOTYPE WORKING (temporary narration)
Video ................... PROTOTYPE WORKING (short experimental clip)

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

<!-- SIRAJ_PRODUCTION_EXCELLENCE_BEGIN -->
## المرجع الاستراتيجي للوصول إلى أعلى مستوى إنتاجي

### الحكم الحالي

- البنية الهندسية للإنتاج أصبحت قابلة لإعادة التشغيل وتعتمد على Manifests.
- المستوى البصري والتحريري الحالي ما يزال أوليًا مقارنة بالمستوى النهائي المطلوب.
- SIRAJ يجب أن يبقى نظام الأوركسترا والتوثيق والتحقق والإخراج النهائي.
- نماذج الذكاء الاصطناعي الخارجية هي مزودو قدرات قابلون للاستبدال، وليست بديلًا عن النظام.

### البنية المستهدفة

SIRAJ مسؤول عن:

- المصادر والمعرفة الموثقة.
- Claim and Evidence Ledger.
- Timeline and Topic Graph.
- كتابة النص وتخطيط الحلقة.
- Editorial Director.
- Timed Scene Planner.
- Visual Policy.
- اختيار مزودي الوسائط.
- Media Asset Registry.
- Quality Gates.
- Final Render and Publication.

يمكن أن يستعين SIRAJ بالمزودين التاليين:

- Language Model Provider.
- Image Provider.
- Video Provider.
- Voice Provider.
- Sound Effect Provider.
- أدوات FFmpeg وProcedural Tools المحلية.

### Hybrid Documentary Engine

لا يجب إنتاج جميع اللقطات بالطريقة نفسها. يختار SIRAJ التقنية الأنسب لكل لقطة:

1. مصادر وصور ثابتة موثقة للمخطوطات والآثار والوثائق.
2. إعادة بناء ثابتة عالية الجودة تتحرك محليًا.
3. خرائط وخطوط زمنية ورسومات Procedural قابلة لإعادة الإنتاج.
4. فيديو مولد للقطات السينمائية المهمة فقط.
5. بطاقات مصادر وادعاءات مرتبطة بالمشهد.
6. مونتاج وصوت نهائي تحت سيطرة SIRAJ.

### ما يبقى داخل SIRAJ

- Historical Knowledge Engine.
- Claim and Evidence Ledger.
- Timeline consistency.
- Script and scene contracts.
- Editorial decisions.
- Provider abstraction.
- Episode Render Manifest.
- Media Asset Registry.
- Islamic visual policy.
- Historical, editorial and technical quality gates.
- Final assembly and publication state.

### ما يسند إلى مزودي الذكاء الاصطناعي

- إعداد مسودات النص ونقدها.
- توليد الصور وإعادة البناء.
- توليد لقطات فيديو قصيرة.
- تحويل النص إلى صوت.
- تنظيف الصوت وتوليد المؤثرات.
- تحليل الوسائط واكتشاف العيوب.
- ترتيب المرشحين وإعادة التوليد.

### سلسلة الإنتاج النهائية

Sources
→ Claims
→ Evidence Review
→ Script
→ Editorial Plan
→ Timed Scenes
→ Voice
→ Visual Assets
→ Audio Layers
→ Episode Render Manifest
→ Local Render Adapter
→ Automated Quality Gates
→ Human Review
→ Publication

### معايير الاحتراف

- صحة الادعاءات واكتمال المصادر.
- اتساق الخط الزمني.
- اتساق العمارة والملابس والبيئة.
- منع العناصر الحديثة أو المختلقة.
- احترام السياسة الشرعية.
- صحة نطق العربية والأسماء.
- جودة الصوت وعدم Clipping.
- تنوع اللقطات وسلامة الإيقاع.
- تطابق الصورة مع النص.
- حقوق الاستخدام والتراخيص.
- إمكانية إعادة إنتاج الحلقة من العقود والأصول المحفوظة.

### قاعدة مزودي الذكاء الاصطناعي

- لا يرتبط النظام بمزود واحد.
- كل مزود يعلن قدراته وتكلفته وزمنه وحدوده.
- يجب توفير Fallback.
- لا يقرر مولد الوسائط الحقائق التاريخية.
- لا تدخل الوسائط المولدة إلى الإنتاج دون Metadata ومراجعة.
- يحفظ النظام Provider وModel وPrompt وSeed وChecksum والترخيص.

### ترتيب التنفيذ الملزم

1. Episode Render Manifest v2.
2. Timed Scene Planner.
3. طبقات الصوت والترجمة.
4. ربط المشاهد بالادعاءات والمصادر والسياسة البصرية.
5. Render Adapter v2.
6. Production VoiceProvider.
7. ImageProvider.
8. Selective VideoProvider.
9. Automated Media Evaluation.
10. الخرائط والرسومات Procedural.
11. Automated Editorial Director.
12. Professional Quality System.
13. إنتاج الحلقة الأولى القابلة للنشر.

### مراحل الوصول إلى أعلى مستوى

#### المرحلة الأولى — Documentary Core

مشاهد موقّتة، طبقات صوت، ترجمة، Source Cards، خرائط وهوية بصرية ثابتة.

#### المرحلة الثانية — AI Media Providers

مزودو الصور والفيديو والصوت والمؤثرات والتقييم مع قابلية الاستبدال ووجود بدائل احتياطية.

#### المرحلة الثالثة — Automated Editorial Director

تحويل النص والأدلة إلى قرارات إخراجية، واختيار المرشحين وتقييمهم ورفض الضعيف وإعادة التوليد.

#### المرحلة الرابعة — Professional Quality System

بوابات تاريخية وشرعية وتحريرية وبصرية وصوتية وتقنية وحقوقية.

#### المرحلة الخامسة — High-End Production

إعادة بناء سينمائية، Motion Graphics، خرائط متحركة، Sound Design، Color Grading واتساق بصري وصوتي عبر الموسم.
<!-- SIRAJ_PRODUCTION_EXCELLENCE_END -->
