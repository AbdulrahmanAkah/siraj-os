# حزمة دستور سراج الموحد 1.1.0

هذه نسخة amendment مقصودة من الإصدار 1.0.0. التغيير الوحيد في السياسة هو إضافة نطاق مقيد يسمح بـShorts burned narration captions المتزامنة مع النص المنطوق؛ تبقى Longform burned captions وon-screen subtitles ممنوعة.

هذه حزمة consolidation + audit + enforcement design فقط. لا تحتوي كودًا إنتاجيًا ولا تمنح إذنًا لأي مزود أو إنفاق أو إعادة إرسال أو مونتاج.

## الملفات

- `SIRAJ_UNIFIED_PRODUCTION_CONSTITUTION_V1.md`: الدستور الموحد القابل للقراءة، الإصدار 1.1.0.
- `siraj_unified_constitution_v1.rules.json`: مصدر القواعد المنظم المقترح للتنفيذ.
- `siraj_unified_constitution_rule_model.schema.json`: مخطط بنية نموذج القواعد.
- `SIRAJ_CONSOLIDATION_AUDIT_AND_ENFORCEMENT_DESIGN_V1.md`: مصفوفة التعارضات والفجوات والإنفاذ والإبطال والقرارات المفتوحة وقرار GO/NO-GO.
- `bundle_manifest.json`: بصمات ملفات الحزمة وحالة حدود المرحلة.

## Amendment: Shorts captions

```text
LONGFORM_BURNED_CAPTIONS = FORBIDDEN
LONGFORM_ON_SCREEN_SUBTITLES = FORBIDDEN
SHORT_DERIVATIVE_BURNED_NARRATION_CAPTIONS = ALLOWED_IF_SYNCED_AND_HASH_BOUND
SHORT_DERIVATIVE_INVENTED_TEXT = FORBIDDEN
```

## القرار

```text
CONSOLIDATION = PASS
GO_FOR_OFFLINE_ENFORCEMENT_IMPLEMENTATION = YES
GO_FOR_PRODUCTION = NO
```

## التحقق المحلي المنجز

```text
JSON_PARSE = PASS
RULE_COUNT = 51
DUPLICATE_RULE_IDS = 0
SECTIONS_PRESENT = 1,2,3,4,5,6,7,8,9,10
INVALIDATION_EVENTS = 14
PRODUCTION_AUTHORIZED = FALSE
```

تعذر تشغيل Validator عام لـJSON Schema لأن مكتبة التحقق غير متاحة محليًا، لذلك أُجري فحص Parse وبنية ومعرفات وأقسام مستقل. يجب أن يكون Schema validation الكامل من أول اختبارات مرحلة التنفيذ.
