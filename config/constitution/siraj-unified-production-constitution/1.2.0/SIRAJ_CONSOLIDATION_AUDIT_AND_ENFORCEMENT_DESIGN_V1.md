# تدقيق توحيد دستور سراج وتصميم الإنفاذ — الإصدار 1.2.0

هذا amendment مقصود للإصدار 1.0.0. لا يغير القواعد الدينية أو البصرية أو حدود الإنفاق؛ يضيف فقط نطاقًا تنفيذيًا مقيدًا لـShorts burned narration captions.

## 1. النتيجة التنفيذية

```text
CONSOLIDATION = PASS
CRITICAL_POLICY_CONTRADICTIONS_UNRESOLVED = 0
HIGH_POLICY_CONTRADICTIONS_UNRESOLVED = 0
CRITICAL_POLICY_AMBIGUITIES_UNRESOLVED = 0
HIGH_POLICY_AMBIGUITIES_UNRESOLVED = 0

GO_FOR_ENFORCEMENT_IMPLEMENTATION = YES
GO_FOR_PROVIDER_OR_PAID_EXECUTION = NO
GO_FOR_RETRY_OR_RESUBMISSION = NO
GO_FOR_MONTAGE = NO
GO_FOR_PRODUCTION = NO
```

الـGO هنا محدود ببناء طبقة الدستور والـCompiler والـValidators والاختبارات والبوابات دون اتصال إنتاجي. لا يصبح الإنتاج مسموحًا إلا بعد إغلاق كل فجوات التنفيذ الحرجة والعالية، واجتياز اختبارات Offline مستقلة، وربط الأصول والموافقات بالبصمات، ثم اعتماد بشري جديد لنطاق الإنتاج نفسه.

## 2. نطاق التدقيق وأدلته

- جُمعت قرارات الأقسام 1–10 من محادثة الاعتماد، مع إعطاء القرارات البشرية اللاحقة أولوية على المسودات السابقة.
- تحقق مباشر من المستودع الحي: الفرع `feature/series-production-quality-v2` عند `7064cdc5036913363a82a57a268a37ff35c3b72e`؛ لا تعديلات tracked ظاهرة، مع عدد كبير من الأدلة والـartifacts غير المتعقبة التي تُركت دون مساس.
- استُخدمت نتائج التدقيق الشامل السابق التي قرأت جميع ملفات HEAD وأثبتت غياب حظر الوجوه العالمي من السلطة التنفيذية، ووجود تعارضات `visible mouth` و`stable faces and anatomy`، وانجراف المدة.
- تحقق مجلد العلامة التجارية مباشرةً: ملف فيديو واحد وملف صورة واحد. عوينت صورة الـOutro بصريًا ولم يظهر فيها وجه بشري؛ وهي تحتوي جرافيكًا ونصوصًا يدخلان في الاستثناء المحدد. أظهر فحص حاوية فيديو الـIntro معالج فيديو H.264 ولم يظهر معالج صوت أو AAC. تعذر عرض الفيديو نفسه داخل أداة المعاينة بسبب سياسة فتح الملفات المحلية، لذلك يبقى فحص جميع إطاراته شرطًا قبل تثبيت بصمته، ولا يُدعى أنه اجتاز التحقق البصري بعد.
- لم تُجر أي Provider call أو paid call أو network production call، ولم يحدث retry أو resubmission أو montage أو تعديل إنتاجي.

## 3. مصفوفة التعارضات

| ID | التعارض أو الالتباس | الحكم الموحد | الشدة قبل الحسم | الحالة |
|---|---|---|---|---|
| CF-01 | صياغات قديمة تمنع وجه النبي فقط مقابل قرار منع جميع الوجوه | `ALL_HUMAN_FACES_VISIBLE = FALSE` لجميع البشر؛ وللأنبياء حظر إضافي مطلق بلا استثناء | Critical | RESOLVED |
| CF-02 | احتمال إظهار عين أو فم لغير النبي | الاستثناء الجزئي غير مفعّل دستوريًا؛ الوجه محجوب بالكامل حاليًا | Critical | RESOLVED |
| CF-03 | `visible mouth` و`stable faces` في V2.4 مقابل الحظر العالمي | العبارتان مخالفتان؛ V2.4 غير صالح للاعتماد أو الإرسال أو المونتاج تحت الإصدار 1.0.0 | Critical | RESOLVED_BY_REJECTION |
| CF-04 | حظر الجرافيك مقابل Intro/Outro الجاهزين | استثناء Whitelist ضيق مرتبط بالملف والبصمة للأصلين فقط؛ لا يمتد لأي جرافيك آخر | Critical | RESOLVED |
| CF-05 | استثناء الجرافيك قد يُفهم أنه يتجاوز حظر الوجه أو الموسيقى | الاستثناء خاص بالجرافيك فقط وتبقى قواعد الوجه والموسيقى أعلى ونافذة على الأصلين | Critical | RESOLVED |
| CF-06 | منع النص داخل الفيديو مقابل Closed Captions وShorts narration captions | Longform burned captions وon-screen subtitles ممنوعة؛ ملف Captions خارجي اختياري؛ ومشتقات Shorts تسمح فقط بـburned narration captions المشتقة من التوقيت الموثوق والمتزامنة مع النطق، مع منع أي نص مخترع | High | RESOLVED_BY_SCOPED_AMENDMENT |
| CF-07 | مسودة صوتية سمحت بالموسيقى مقابل القرار البشري النهائي | القرار اللاحق ينسخ المسودة: الموسيقى ممنوعة في كل المواضع بلا استثناء | Critical | RESOLVED |
| CF-08 | السماح بكل أنواع SFX مقابل منع اختراع حدث غير مثبت | لا حظر لفئة المؤثر، لكن الاستعمال يجب أن يخدم السرد وألا يقدم حقيقة غيبية/تاريخية مختلقة | High | RESOLVED |
| CF-09 | بنية متعددة المزودات مقابل Veo 3.1 Lite مزودًا أساسيًا | البنية قابلة للتوسع، لكن السلطة الإنتاجية الحالية لـVeo 3.1 Lite وحده؛ البديل تجريبي حتى طيار وموافقة | High | RESOLVED |
| CF-10 | هدف منع الإعادة مقابل وجود مسار Retry | لا إعادة تلقائية أو مطابقة؛ المسار الاستثنائي يحتاج سببًا جذريًا وإصلاحًا جوهريًا وPreflight وتفويضًا جديدًا | Critical | RESOLVED |
| CF-11 | حالة UNKNOWN قد تُعامل كفشل تقني قابل للإعادة | UNKNOWN حالة مستقلة؛ مصالحة فقط ولا إعادة أو استئناف | Critical | RESOLVED |
| CF-12 | نسبة الفيديو 50–75% مقابل إضافة Intro/Outro | المقام هو `CORE_EPISODE_DURATION` فقط؛ الأصلان خارج حساب النسبة | High | RESOLVED |
| CF-13 | مدة الحلقة 8–15 مقابل Runtime المنشور | النطاق يخص جسم الحلقة؛ `PUBLISHED_RUNTIME = CORE + INTRO + OUTRO` | High | RESOLVED |
| CF-14 | صورة Canonical للشخصية مقابل حظر الوجه | المرجع نفسه ملزم بحظر الوجه والستر والحقبة؛ الهوية تُقفل بغير ملامح الوجه | Critical | RESOLVED |
| CF-15 | أصالة حقبة آدم مقابل غياب معلومات أثرية محددة | يُمنع الحديث؛ ويُستخدم إخراج محايد في المجهول دون اختراع «زي تاريخي» مزعوم | High | RESOLVED |
| CF-16 | التوثيق الكامل مقابل منع بطاقات المصادر | التوثيق الخلفي كامل، والإفصاح المطلوب للمشاهد يندمج في صوت الراوي | High | RESOLVED |
| CF-17 | العنوان والـThumbnail غير مطلوبين لإنتاج الحلقة مقابل النشر | لا يدخلان Episode Production Pass؛ لكنهما ملك بشري، ويحظر نشر عنوان العمل أو النشر الذاتي | Critical | RESOLVED |
| CF-18 | وضع Intro تلقائيًا مقابل قرار المخرج | الإدراج إلزامي، والموضع يختاره المخرج/الخطة المعتمدة بشرط عدم قطع جملة أو فعل أو إضعاف الـHook | High | RESOLVED |
| CF-19 | نجاح المزود مقابل أهلية المونتاج | نجاح API أو اكتمال المزود لا يكفي؛ يلزم فحص الناتج الحقيقي ثم اعتماده | Critical | RESOLVED |
| CF-20 | أرقام مدة متعددة | سلطة واحدة: قياس ملف Narration Master المعتمد بدقة موحدة؛ أي Cache مخالف يفشل | Critical | RESOLVED |
| CF-21 | Human-readable وMachine-readable مع ادعاء SHA واحد | بصمة مستقلة لكل ملف وبصمة Manifest للحزمة؛ هوية وإصدار واحدان دون ادعاء تطابق Bytes مختلفة | High | RESOLVED |
| CF-22 | منع المونتاج في هذه المرحلة مقابل وجود قسم مونتاج دائم | المنع الحالي حد مرحلة؛ القسم 7 يحدد شروط المونتاج المستقبلي ولا يمنح إذنًا الآن | High | RESOLVED |

## 4. مصفوفة الفجوات والإنفاذ

الحالات:

```text
EXISTING_PARTIAL = توجد آلية حالية لكنها لا تغلق العقد الموحد
MISSING = لا توجد آلية مثبتة تحقق العقد
DESIGNED = صُممت هنا دون تنفيذ
BLOCKS_PRODUCTION = يمنع الإنتاج حتى الإغلاق والتحقق
```

| مجموعة القواعد | Compiler | Validator | Tests | Runtime Gate | الحالة الحالية | شرط الإغلاق |
|---|---|---|---|---|---|---|
| حظر جميع الوجوه | حقن عالمي ومنع الدلالات الإيجابية | عقد + مراجع + كل الإطارات + إنسان | مرادفات/خلفية/انعكاس/جزئي | Storyboard→Prompt→Submit→Render→Montage | MISSING/CONFLICTING | تنفيذ مستقل Fail-Closed وإثبات اختبارات سلبية؛ BLOCKS_PRODUCTION |
| حظر وجه النبي | قفل غير قابل للتجاوز | Sacred + face validators | عين/فم/profile/انعكاس | جميع البوابات البصرية | EXISTING_PARTIAL | رفعه إلى العقد الموحد وربطه بكل المراحل |
| الغيب وعدم التجسيد | Observable consequence | Source + theological + visual | أشكال وآليات غير مسندة | Research/Storyboard/Prompt/Render | EXISTING_PARTIAL | ربط الأدلة بالـPrompt والناتج |
| الستر | Wardrobe contract | Contract + frame scan + human | جلد/ضيق/شفاف/حذف شخصية | Character/Prompt/Render/Montage | EXISTING_PARTIAL | توحيد عقد السلسلة ومنع bypass |
| أصالة الحقبة | Period dossier injection | Evidence/storyboard/prompt/render | Anachronism/unknown neutrality | Research→Render | EXISTING_PARTIAL | ملف حقبي منظم لكل حقبة وفئات يقين |
| Canonical character still | Reference hash binding | Provenance + continuity | Missing/drift/failed reference | Character/Prompt/Pilot/Render | MISSING_GLOBALLY | بناء القفل العام؛ BLOCKS_RECURRING_CHARACTER_PRODUCTION |
| هرمية المصادر | Carry tier/certainty | Claim ledger + source hierarchy | Override/unsourced/certainty upgrade | Research/Script/Final source QA | EXISTING_PARTIAL | مصدر واحد لمصفوفة الادعاءات وربطها downstream |
| الإسرائيليات/الضعيف/الخلاف | صياغة يقين مقيدة | تصنيف + مراجعة بشرية مختصة | جزم/تعارض/إخفاء خلاف | Research/Script | DESIGNED | تعريف Receipts للمراجع البشري ونطاق القرار |
| حظر الجرافيك | Exclude graphic plans | Storyboard/render/montage | Overlay/cards/diagram | Storyboard/Render/Montage | EXISTING_STRONG | إضافة Whitelist محكم للأصلين فقط |
| جودة السرد والمدة | Beat/claim/duration plan | Structure + human editorial | False hook/filler/out-of-range | Script/Narration/Final quality | EXISTING_PARTIAL | قواعد مدة وحشو واختبارات وتبرير الاستثناء |
| نص الأداء العربي | Contextual pronunciation compiler | Semantic/diacritics/waqf/wasl | Ambiguity/blind stripping | TTS/Narration master | EXISTING_PARTIAL | قاموس سلسلة وعقد Pause/Waqf وصوت معتمد |
| مطابقة الصورة للمعنى | Shot-to-beat compiler | Mute comprehension + render semantics | Inversion/missing action/filler | Storyboard/Render/Montage | EXISTING_STRONG_PARTIAL | توحيدها مع الحظر العالمي والمصادر |
| نسبة الفيديو | Timeline planner | Media-share + core-runtime | أقل/أكثر/تزييف بالمقدمة | Storyboard/Montage/Final QA | MISSING_UNIFIED | حساب موحد من Core duration |
| Hard-shot pilot | Risk classifier | Coverage + all-frame + human | Easy-only/new risk class | Pilot/Paid batch | EXISTING_PARTIAL | تعريف Risk classes وإبطال الطيار عند فئة جديدة |
| Prompt compilation | Structured compiler بلا شبكة | Semantic linter + exact payload hash | Freeform weakening/missing binding | Compile/Human review/Submit | MISSING_AS_ROOT_AUTHORITY | بناء Compiler من النموذج الموحد؛ BLOCKS_PROVIDER |
| مزود/model profile | لا fallback | Profile + approval | Silent switch/model alias | Selection/Pilot/Paid | EXISTING_PARTIAL | ربط الاسم الدستوري بمعرف API وإصدار وأسعار معتمد |
| Progressive batching | Risk partition | Pilot dependency + scope | Unbounded/unpiloted risk | Batch authorization/review | EXISTING_PARTIAL | آلة حالات دفعات وموافقة مستقلة |
| الموسيقى/SFX | Music exclusion + SFX purpose | Audio stream/content/semantic/sync | Music anywhere/false event | Asset/Mix/Final audio | MISSING_UNIFIED | فحص كل الأصول والمكس؛ BLOCKS_FINAL_AUDIO |
| سلطة الصوت والمدة | Derive from master | Hash + duration + precision | Cache drift/audio change | Narration/Timeline/Montage | CONFLICTING_CURRENT_DATA | عقد قياس واحد وإبطال شامل؛ BLOCKS_EP002_TIMELINE |
| Intro/Outro | Discovery + placement plan | Cardinality/hash/policy/placement | Ambiguity/hash drift/bad boundary | Binding/Montage/Final QA | ASSETS_PRESENT_DESIGN_ONLY | فحص بصري كامل ثم SHA وربط؛ لا تعديل للأصلين |
| الاعتماد النهائي | لا ينطبق | Domain + candidate hash + human receipt | Automated/partial/stale | Publish-ready/publication | EXISTING_PARTIAL | بوابة واحدة على Final Candidate نفسه |
| العنوان والـThumbnail | Keep internal only | Metadata boundary | Working-title leak/thumbnail generation | Publication package | MISSING_UNIFIED | منع القدرة الآلية وإبقاء الملكية بشرية |
| Paid Desktop click | لا ينطبق | Origin + click nonce + envelope | Terminal/CLI/recovery/test | Paid execution | EXISTING_STRONG_PARTIAL | ربطه بالدستور الجديد وكل hashes |
| التكلفة | لا ينطبق | Rate/estimate/ceiling/staleness | Changed scope/rate/anomaly | Cost/Paid/Anomaly | EXISTING_PARTIAL | Profile أسعار حديث وAuthorization envelope |
| UNKNOWN/reconciliation | لا ينطبق | State + ledger head + receipt | Unknown-as-failed/resubmit | Reconcile/Retry/Paid | EXISTING_STRONG | الحفاظ Append-Only وربطه بالحزمة الجديدة |
| Idempotency/double click | لا ينطبق | Attempt uniqueness + consumption | Duplicate click/reuse auth | Transaction lock/Paid | EXISTING_PARTIAL | Nonce ومعاملة ذرية وسجل استهلاك |
| سلطة دستورية واحدة | Load/compile bundle | Manifest/precedence/duplicates | Missing/hash/weakening/default | Boot/every stage | MISSING | أول حزمة تنفيذية؛ BLOCKS_ALL_PRODUCTION |
| Approval invalidation | لا ينطبق | Receipt + DAG + stale state | كل تغير مادي | Every promotion/paid/publish | EXISTING_PARTIAL | Graph موحد وحساب transitive invalidation |
| فصل الصلاحيات | Compiler offline | Capability/dependency/network | No provider in compiler/tests/recovery | Boot/Pre-submit | MISSING_UNIFIED | حدود Dependencies واختبارات Capability |

## 5. نموذج الاعتماد والإبطال

### 5.1 سلسلة الاعتماد

```text
CONSTITUTION BUNDLE
→ SOURCE / CLAIM LEDGER
→ PERIOD + CHARACTER DOSSIERS
→ CANONICAL SCRIPT
→ TTS PERFORMANCE SCRIPT + LEXICON
→ NARRATION MASTER
→ TIMELINE + STORYBOARD
→ FINAL PROVIDER PAYLOADS + REFERENCES
→ HARD-SHOT PILOT
→ PROGRESSIVE BATCH AUTHORIZATION
→ RENDER CONFORMANCE + PROMOTION
→ MONTAGE PLAN + FINAL CANDIDATE
→ DOMAIN QA + TWO MONTAGE REVIEWS
→ FINAL HUMAN CERTIFICATION
→ HUMAN-CONTROLLED PUBLICATION BOUNDARY
```

### 5.2 الحد الأدنى لوصل الموافقة

كل Receipt يسجل:

```text
APPROVAL_ID
APPROVAL_TYPE
HUMAN_ACTOR
DECISION
DECISION_TIME
CONSTITUTION_BUNDLE_MANIFEST_SHA256
INPUT_ARTIFACT_IDS
INPUT_SHA256S
SCOPE
STALE_ON_EVENTS
CONSUMED_BY_TRANSACTION_ID_IF_ANY
```

لا ترث نسخة جديدة موافقة نسخة سابقة لمجرد تشابه الاسم أو المسار.

### 5.3 جدول الإبطال

| التغيير | ما يُبطل حتمًا |
|---|---|
| الدستور أو Manifest | كل الموافقات والـcompiled bundles التابعة |
| مصدر أو ادعاء أو درجة يقين | النص وما بعده حتى الاعتماد النهائي |
| النص المعتمد | نص الأداء والصوت والتوقيت والصورة والإنفاق والمونتاج والنهاية |
| نص الأداء أو القاموس أو محرك TTS جوهريًا | اعتماد الصوت والـNarration Master وما بعده |
| Bytes ملف Narration Master | التايملاين والـStoryboard والبرومبتات والتكلفة والطيار والتفويض والمونتاج والنهاية |
| ملف الشخصية/الحقبة/اللباس | الـStoryboard والبرومبت والطيار والتفويض والناتج والمونتاج |
| Canonical Still أو بصمته | البرومبت والطيار والتفويض والناتج والمونتاج |
| الـStoryboard | البرومبت والطيار والتفويض والناتج والمونتاج |
| البرومبت أو المرجع أو الإعدادات | مراجعة البرومبت والطيار والتفويض |
| المزود أو النموذج أو الأسعار | الطيار وتقدير التكلفة والتفويض |
| عدد الطلبات أو نطاق الدفعة | التكلفة والتفويض |
| ظهور فئة خطر جديدة | تغطية الطيار وتفويض الدفعة |
| Bytes الناتج | Render QA والمونتاج والاعتماد النهائي |
| Intro/Outro | اعتماد أصل العلامة والمونتاج والاعتماد النهائي |
| Final Candidate | كل Final QA والاعتماد البشري النهائي |
| العنوان العام أو الـThumbnail اليدويان | لا يبطلان Episode Production Pass؛ يبقيان ضمن مسؤولية النشر البشري |

المصالحة لا تُنشئ موافقة، وتحديث حالة UNKNOWN لا يسمح بالإرسال إلا بعد حسم الحالة ثم إنشاء مسار تفويض جديد مستقل إذا كان مطلوبًا.

## 6. القرارات غير المحسومة

### 6.1 Critical / High

```text
UNRESOLVED_CRITICAL_POLICY_DECISIONS = 0
UNRESOLVED_HIGH_POLICY_DECISIONS = 0
```

المسائل الحرجة والعالية حُسمت إما بقاعدة صريحة أو برفض المادة المخالفة أو ببوابة Fail-Closed. وجود عمل برمجي غير منفذ لا يُعاد توصيفه كغموض دستوري؛ لكنه يبقى مانعًا للإنتاج.

### 6.2 معاملات تنفيذية مؤجلة لا تغيّر الحكم الدستوري

| ID | المعامل | المستوى | الحكم الحالي |
|---|---|---|---|
| OPEN-M01 | القيمة العددية لـIntegrated Loudness وTrue Peak | Medium | يجب تثبيتها في Technical Delivery Profile قبل اعتماد الصوت؛ غيابها يحجب Final Audio Pass |
| OPEN-M02 | معرف API الدقيق وإصدار Profile المقابل لـVeo 3.1 Lite | Medium | الاسم الدستوري ثابت؛ لا اتصال مدفوع قبل ربط معرف دقيق واعتماده بلا alias أو fallback صامت |
| OPEN-M03 | عتبات أدوات كشف الوجه وتغطية الإطارات | Medium implementation parameter | القاعدة لا تتغير: أي uncertainty تُنتج BLOCKED، ولا تخفض العتبة لتجاوز مادة؛ يلزم اختبار recall وnegative corpus قبل الإنتاج |
| OPEN-L01 | بصمتا Intro وOutro | Deferred implementation fact | تُحسب لاحقًا عند التنفيذ كما طُلب؛ تغير العدد أو الملف أو البصمة يوقف المونتاج |
| OPEN-L02 | نتيجة الفحص البصري الكامل لفيديو Intro | Deferred asset validation | يجب فحص كل الإطارات قبل ربط البصمة؛ عدم اكتمال الفحص يمنع Brand Asset Pass ولا يخلق استثناءً |

## 7. شروط الانتقال الآمن إلى التنفيذ

المسموح في المرحلة التالية فقط:

1. تنفيذ Loader/Schema/Compiler/Validators/Gates/Receipts/Dependency Graph وFixtures محلية.
2. بناء اختبارات إيجابية وسلبية واختبارات منع القدرة الشبكية والمدفوعة.
3. توليد Coverage Manifest يثبت لكل Hard Rule المسار الكامل `Rule→Compiler→Validator→Test→Runtime Gate` أو سبب عدم الانطباق.
4. تشغيل الاختبارات Offline فقط وبمزودات Fakes.
5. عدم تعديل أو حذف الأدلة والـartifacts القديمة، وعدم جعل V2.4 أو أي موافقة قديمة صالحة تلقائيًا.

ويظل ممنوعًا حتى شهادة تنفيذ مستقلة:

```text
PROVIDER_CALL
PAID_CALL
NETWORK_PRODUCTION_CALL
RETRY
RESUBMISSION
MONTAGE
PRODUCTION_EXECUTION
PUBLICATION
```

## 8. قرار GO / NO-GO النهائي

```text
CONSOLIDATION_AUDIT_ENFORCEMENT_DESIGN = PASS

NEXT_PHASE = GO
NEXT_PHASE_SCOPE = OFFLINE_ENFORCEMENT_IMPLEMENTATION_ONLY

PRODUCTION = NO_GO
EP002_V2_4 = NO_GO
PAID_EXECUTION = NO_GO
PROVIDER_EXECUTION = NO_GO
MONTAGE = NO_GO
```

سبب الـGO المحدود: لا يوجد تعارض أو غموض دستوري Critical/High غير محسوم، والمخرجات تحدد السلطة وسلسلة الإنفاذ والإبطال والحدود. سبب NO-GO الإنتاجي: الكود الحالي لم يُثبت بعد أنه ينفذ هذه الحزمة، والتدقيق السابق أثبت تعارضًا مباشرًا مع حظر الوجوه وانجرافًا في سلطة المدة، كما لم تُربط أصول العلامة بالبصمات ولم يُغلق Coverage Manifest.

---

# ملحق مراجعة 1.2.0 — Six Fixes Only

التغيير الدستوري الحالي محصور في:
`C2, C3, C6, C8, H3, H4`.

- C2: scoped production authorization; no blanket global production grant.
- C3: إزالة هوية محاولة EP002 من القانون العالمي والإبقاء على قاعدة UNKNOWN العامة.
- C6: burned narration captions للـShorts فقط؛ Long-form يبقى ممنوعًا.
- C8: مسار الحزمة يطابق الإصدار 1.2.0.
- H3: hard fail للمفارقة التاريخية المادية الواضحة؛ التفاصيل الثانوية غير المؤكدة weighted.
- H4: pilot مشروط بالمخاطر وليس blanket requirement لكل حلقة.

`C7` محفوظ بلا تغيير.
