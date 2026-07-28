"""Materialize an externally researched source-candidate pack for Adam.

The pack covers all fourteen unresolved factual non-Quran events. It provides
source locators, normalized Arabic anchors, claim scopes, event/source links,
and deterministic checksums. It is a candidate layer only: it does not assert
that a remote page was human-compared, authenticate reports, grade hadith,
classify origin conclusively, approve narration, open evidence gates, or enable
providers.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Mapping

CATALOG_SCHEMA = "siraj-external-source-candidate-catalog-v1"
PACK_SCHEMA = "siraj-external-event-source-candidate-pack-v1"
POLICY_SCHEMA = "siraj-external-source-candidate-policy-v1"
REVIEW_SCHEMA = "siraj-external-source-human-review-template-v1"
MATCH_SCHEMA = "siraj-external-source-auto-match-ledger-v1"
RECORD_SCHEMA = "siraj-external-source-candidate-record-v1"
STATUS = "EXTERNAL_SOURCE_CANDIDATES_MATERIALIZED_HUMAN_VERIFICATION_PENDING"
GATE = "WITHHELD_PENDING_APPROVED_EVIDENCE_PACKAGE"
AUTO_APPROVAL = "FORBIDDEN"
LIVE_EXECUTION = "BLOCKED"
RESEARCH_DATE = "2026-07-28"

FACTUAL_EVENTS = (
    "EV-ADAM-001", "EV-ADAM-002", "EV-ADAM-003", "EV-ADAM-005",
    "EV-ADAM-007", "EV-ADAM-021", "EV-ADAM-023", "EV-ADAM-024",
    "EV-ADAM-032", "EV-ADAM-033", "EV-ADAM-042", "EV-ADAM-060",
    "EV-ADAM-061", "EV-ADAM-070",
)

SOURCE_RECORDS = (
    {
        "source_candidate_id": "SRC-BUKHARI-3191",
        "source_kind": "HADITH_COLLECTION_RECORD",
        "collection": "Sahih al-Bukhari",
        "collection_ar": "صحيح البخاري",
        "compiler": "Muhammad ibn Ismail al-Bukhari",
        "compiler_ar": "محمد بن إسماعيل البخاري",
        "locator": "Sahih al-Bukhari 3191",
        "record_number": "3191",
        "source_url": "https://sunnah.com/bukhari:3191",
        "arabic_anchor_text": (
            "كان الله ولم يكن شيء غيره وكان عرشه على الماء "
            "وكتب في الذكر كل شيء وخلق السماوات والأرض"
        ),
        "proposed_origin_classification": "authentic_sunnah",
        "authority_tier_candidate": "SAHIH_COLLECTION_RECORD",
        "aliases": ["البخاري", "صحيح البخاري", "Bukhari", "Sahih al-Bukhari"],
    },
    {
        "source_candidate_id": "SRC-MUSLIM-2653B",
        "source_kind": "HADITH_COLLECTION_RECORD",
        "collection": "Sahih Muslim",
        "collection_ar": "صحيح مسلم",
        "compiler": "Muslim ibn al-Hajjaj",
        "compiler_ar": "مسلم بن الحجاج",
        "locator": "Sahih Muslim 2653b",
        "record_number": "2653",
        "source_url": "https://sunnah.com/muslim:2653b",
        "arabic_anchor_text": (
            "كتب الله مقادير الخلائق قبل أن يخلق السماوات والأرض "
            "بخمسين ألف سنة وكان عرشه على الماء"
        ),
        "proposed_origin_classification": "authentic_sunnah",
        "authority_tier_candidate": "SAHIH_COLLECTION_RECORD",
        "aliases": ["مسلم", "صحيح مسلم", "Muslim", "Sahih Muslim"],
    },
    {
        "source_candidate_id": "SRC-ABUDAWUD-4700",
        "source_kind": "HADITH_COLLECTION_RECORD",
        "collection": "Sunan Abi Dawud",
        "collection_ar": "سنن أبي داود",
        "compiler": "Abu Dawud al-Sijistani",
        "compiler_ar": "أبو داود السجستاني",
        "locator": "Sunan Abi Dawud 4700",
        "record_number": "4700",
        "source_url": "https://sunnah.com/abudawud:4700",
        "arabic_anchor_text": (
            "إن أول ما خلق الله القلم فقال له اكتب قال رب وماذا أكتب "
            "قال اكتب مقادير كل شيء حتى تقوم الساعة"
        ),
        "proposed_origin_classification": "authentic_sunnah",
        "authority_tier_candidate": "SUNAN_RECORD_AUTHORITY_REVIEW_REQUIRED",
        "aliases": ["أبو داود", "سنن أبي داود", "Abu Dawud", "Sunan Abi Dawud"],
    },
    {
        "source_candidate_id": "SRC-TIRMIDHI-2155",
        "source_kind": "HADITH_COLLECTION_RECORD",
        "collection": "Jami at-Tirmidhi",
        "collection_ar": "جامع الترمذي",
        "compiler": "Muhammad ibn Isa al-Tirmidhi",
        "compiler_ar": "محمد بن عيسى الترمذي",
        "locator": "Jami at-Tirmidhi 2155",
        "record_number": "2155",
        "source_url": "https://sunnah.com/tirmidhi:2155",
        "arabic_anchor_text": (
            "إن أول ما خلق الله القلم فقال اكتب فقال ما أكتب "
            "قال اكتب القدر ما كان وما هو كائن إلى الأبد"
        ),
        "proposed_origin_classification": "authentic_sunnah",
        "authority_tier_candidate": "SUNAN_RECORD_AUTHORITY_REVIEW_REQUIRED",
        "aliases": ["الترمذي", "جامع الترمذي", "Tirmidhi", "Jami at-Tirmidhi"],
    },
    {
        "source_candidate_id": "SRC-MUSLIM-2996",
        "source_kind": "HADITH_COLLECTION_RECORD",
        "collection": "Sahih Muslim",
        "collection_ar": "صحيح مسلم",
        "compiler": "Muslim ibn al-Hajjaj",
        "compiler_ar": "مسلم بن الحجاج",
        "locator": "Sahih Muslim 2996",
        "record_number": "2996",
        "source_url": "https://sunnah.com/muslim:2996",
        "arabic_anchor_text": (
            "خلقت الملائكة من نور وخلق الجان من مارج من نار "
            "وخلق آدم مما وصف لكم"
        ),
        "proposed_origin_classification": "authentic_sunnah",
        "authority_tier_candidate": "SAHIH_COLLECTION_RECORD",
        "aliases": ["مسلم", "صحيح مسلم", "Muslim", "Sahih Muslim"],
    },
    {
        "source_candidate_id": "SRC-QURAN-002-034",
        "source_kind": "QURAN_VERSE",
        "collection": "Quran",
        "collection_ar": "القرآن الكريم",
        "compiler": "",
        "compiler_ar": "",
        "locator": "Quran 2:34",
        "record_number": "2:34",
        "source_url": "https://quran.com/2/34",
        "arabic_anchor_text": (
            "وإذ قلنا للملائكة اسجدوا لآدم فسجدوا إلا إبليس "
            "أبى واستكبر وكان من الكافرين"
        ),
        "proposed_origin_classification": "quran_explicit",
        "authority_tier_candidate": "QURAN_REFERENCE_ANCHOR",
        "aliases": ["القرآن", "سورة البقرة", "Quran", "Al-Baqarah"],
    },
    {
        "source_candidate_id": "SRC-QURAN-018-050",
        "source_kind": "QURAN_VERSE",
        "collection": "Quran",
        "collection_ar": "القرآن الكريم",
        "compiler": "",
        "compiler_ar": "",
        "locator": "Quran 18:50",
        "record_number": "18:50",
        "source_url": "https://quran.com/18/50",
        "arabic_anchor_text": (
            "وإذ قلنا للملائكة اسجدوا لآدم فسجدوا إلا إبليس "
            "كان من الجن ففسق عن أمر ربه"
        ),
        "proposed_origin_classification": "quran_explicit",
        "authority_tier_candidate": "QURAN_REFERENCE_ANCHOR",
        "aliases": ["القرآن", "سورة الكهف", "Quran", "Al-Kahf"],
    },
    {
        "source_candidate_id": "SRC-QURAN-015-027",
        "source_kind": "QURAN_VERSE",
        "collection": "Quran",
        "collection_ar": "القرآن الكريم",
        "compiler": "",
        "compiler_ar": "",
        "locator": "Quran 15:27",
        "record_number": "15:27",
        "source_url": "https://quran.com/15/27",
        "arabic_anchor_text": "والجان خلقناه من قبل من نار السموم",
        "proposed_origin_classification": "quran_explicit",
        "authority_tier_candidate": "QURAN_REFERENCE_ANCHOR",
        "aliases": ["القرآن", "سورة الحجر", "Quran", "Al-Hijr"],
    },
    {
        "source_candidate_id": "SRC-QURAN-003-059",
        "source_kind": "QURAN_VERSE",
        "collection": "Quran",
        "collection_ar": "القرآن الكريم",
        "compiler": "",
        "compiler_ar": "",
        "locator": "Quran 3:59",
        "record_number": "3:59",
        "source_url": "https://quran.com/3/59",
        "arabic_anchor_text": (
            "إن مثل عيسى عند الله كمثل آدم خلقه من تراب "
            "ثم قال له كن فيكون"
        ),
        "proposed_origin_classification": "quran_explicit",
        "authority_tier_candidate": "QURAN_REFERENCE_ANCHOR",
        "aliases": ["القرآن", "سورة آل عمران", "Quran", "Ali Imran"],
    },
    {
        "source_candidate_id": "SRC-QURAN-015-026",
        "source_kind": "QURAN_VERSE",
        "collection": "Quran",
        "collection_ar": "القرآن الكريم",
        "compiler": "",
        "compiler_ar": "",
        "locator": "Quran 15:26",
        "record_number": "15:26",
        "source_url": "https://quran.com/15/26",
        "arabic_anchor_text": (
            "ولقد خلقنا الإنسان من صلصال من حمإ مسنون"
        ),
        "proposed_origin_classification": "quran_explicit",
        "authority_tier_candidate": "QURAN_REFERENCE_ANCHOR",
        "aliases": ["القرآن", "سورة الحجر", "Quran", "Al-Hijr"],
    },
    {
        "source_candidate_id": "SRC-QURAN-037-011",
        "source_kind": "QURAN_VERSE",
        "collection": "Quran",
        "collection_ar": "القرآن الكريم",
        "compiler": "",
        "compiler_ar": "",
        "locator": "Quran 37:11",
        "record_number": "37:11",
        "source_url": "https://quran.com/37/11",
        "arabic_anchor_text": (
            "فاستفتهم أهم أشد خلقا أم من خلقنا إنا خلقناهم "
            "من طين لازب"
        ),
        "proposed_origin_classification": "quran_explicit",
        "authority_tier_candidate": "QURAN_REFERENCE_ANCHOR",
        "aliases": ["القرآن", "سورة الصافات", "Quran", "As-Saffat"],
    },
    {
        "source_candidate_id": "SRC-QURAN-055-014",
        "source_kind": "QURAN_VERSE",
        "collection": "Quran",
        "collection_ar": "القرآن الكريم",
        "compiler": "",
        "compiler_ar": "",
        "locator": "Quran 55:14",
        "record_number": "55:14",
        "source_url": "https://quran.com/55/14",
        "arabic_anchor_text": "خلق الإنسان من صلصال كالفخار",
        "proposed_origin_classification": "quran_explicit",
        "authority_tier_candidate": "QURAN_REFERENCE_ANCHOR",
        "aliases": ["القرآن", "سورة الرحمن", "Quran", "Ar-Rahman"],
    },
    {
        "source_candidate_id": "SRC-QURAN-038-071",
        "source_kind": "QURAN_VERSE",
        "collection": "Quran",
        "collection_ar": "القرآن الكريم",
        "compiler": "",
        "compiler_ar": "",
        "locator": "Quran 38:71",
        "record_number": "38:71",
        "source_url": "https://quran.com/38/71",
        "arabic_anchor_text": (
            "إذ قال ربك للملائكة إني خالق بشرا من طين"
        ),
        "proposed_origin_classification": "quran_explicit",
        "authority_tier_candidate": "QURAN_REFERENCE_ANCHOR",
        "aliases": ["القرآن", "سورة ص", "Quran", "Sad"],
    },
    {
        "source_candidate_id": "SRC-MUSLIM-2611A",
        "source_kind": "HADITH_COLLECTION_RECORD",
        "collection": "Sahih Muslim",
        "collection_ar": "صحيح مسلم",
        "compiler": "Muslim ibn al-Hajjaj",
        "compiler_ar": "مسلم بن الحجاج",
        "locator": "Sahih Muslim 2611a",
        "record_number": "2611",
        "source_url": "https://sunnah.com/muslim:2611a",
        "arabic_anchor_text": (
            "لما صور الله آدم في الجنة تركه ما شاء الله أن يتركه "
            "فجعل إبليس يطيف به ينظر ما هو"
        ),
        "proposed_origin_classification": "authentic_sunnah",
        "authority_tier_candidate": "SAHIH_COLLECTION_RECORD",
        "aliases": ["مسلم", "صحيح مسلم", "Muslim", "Sahih Muslim"],
    },
    {
        "source_candidate_id": "SRC-BUKHARI-3326",
        "source_kind": "HADITH_COLLECTION_RECORD",
        "collection": "Sahih al-Bukhari",
        "collection_ar": "صحيح البخاري",
        "compiler": "Muhammad ibn Ismail al-Bukhari",
        "compiler_ar": "محمد بن إسماعيل البخاري",
        "locator": "Sahih al-Bukhari 3326",
        "record_number": "3326",
        "source_url": "https://sunnah.com/bukhari:3326",
        "arabic_anchor_text": (
            "خلق الله آدم وطوله ستون ذراعا ثم قال اذهب فسلم "
            "على أولئك من الملائكة فاستمع ما يحيونك"
        ),
        "proposed_origin_classification": "authentic_sunnah",
        "authority_tier_candidate": "SAHIH_COLLECTION_RECORD",
        "aliases": ["البخاري", "صحيح البخاري", "Bukhari", "Sahih al-Bukhari"],
    },
    {
        "source_candidate_id": "SRC-MUSLIM-2841",
        "source_kind": "HADITH_COLLECTION_RECORD",
        "collection": "Sahih Muslim",
        "collection_ar": "صحيح مسلم",
        "compiler": "Muslim ibn al-Hajjaj",
        "compiler_ar": "مسلم بن الحجاج",
        "locator": "Sahih Muslim 2841",
        "record_number": "2841",
        "source_url": "https://sunnah.com/muslim:2841",
        "arabic_anchor_text": (
            "خلق الله عز وجل آدم على صورته طوله ستون ذراعا "
            "فلما خلقه قال اذهب فسلم على أولئك النفر"
        ),
        "proposed_origin_classification": "authentic_sunnah",
        "authority_tier_candidate": "SAHIH_COLLECTION_RECORD",
        "aliases": ["مسلم", "صحيح مسلم", "Muslim", "Sahih Muslim"],
    },
    {
        "source_candidate_id": "SRC-QURAN-002-031-033",
        "source_kind": "QURAN_VERSE_RANGE",
        "collection": "Quran",
        "collection_ar": "القرآن الكريم",
        "compiler": "",
        "compiler_ar": "",
        "locator": "Quran 2:31-33",
        "record_number": "2:31-33",
        "source_url": "https://quran.com/2/31-33",
        "arabic_anchor_text": (
            "وعلم آدم الأسماء كلها ثم عرضهم على الملائكة | "
            "قالوا سبحانك لا علم لنا إلا ما علمتنا | "
            "قال يا آدم أنبئهم بأسمائهم فلما أنبأهم بأسمائهم"
        ),
        "proposed_origin_classification": "quran_explicit",
        "authority_tier_candidate": "QURAN_REFERENCE_ANCHOR",
        "aliases": ["القرآن", "سورة البقرة", "Quran", "Al-Baqarah"],
    },
    {
        "source_candidate_id": "SRC-QURAN-007-172",
        "source_kind": "QURAN_VERSE",
        "collection": "Quran",
        "collection_ar": "القرآن الكريم",
        "compiler": "",
        "compiler_ar": "",
        "locator": "Quran 7:172",
        "record_number": "7:172",
        "source_url": "https://quran.com/7/172",
        "arabic_anchor_text": (
            "وإذ أخذ ربك من بني آدم من ظهورهم ذريتهم وأشهدهم "
            "على أنفسهم ألست بربكم قالوا بلى شهدنا"
        ),
        "proposed_origin_classification": "quran_explicit",
        "authority_tier_candidate": "QURAN_REFERENCE_ANCHOR",
        "aliases": ["القرآن", "سورة الأعراف", "Quran", "Al-Araf"],
    },
    {
        "source_candidate_id": "SRC-TIRMIDHI-3076",
        "source_kind": "HADITH_COLLECTION_RECORD",
        "collection": "Jami at-Tirmidhi",
        "collection_ar": "جامع الترمذي",
        "compiler": "Muhammad ibn Isa al-Tirmidhi",
        "compiler_ar": "محمد بن عيسى الترمذي",
        "locator": "Jami at-Tirmidhi 3076",
        "record_number": "3076",
        "source_url": "https://sunnah.com/tirmidhi:3076",
        "arabic_anchor_text": (
            "لما خلق الله آدم مسح ظهره فسقط من ظهره كل نسمة "
            "هو خالقها من ذريته إلى يوم القيامة"
        ),
        "proposed_origin_classification": "authentic_sunnah",
        "authority_tier_candidate": "SUNAN_RECORD_AUTHORITY_REVIEW_REQUIRED",
        "aliases": ["الترمذي", "جامع الترمذي", "Tirmidhi", "Jami at-Tirmidhi"],
    },
    {
        "source_candidate_id": "SRC-QURAN-004-001",
        "source_kind": "QURAN_VERSE",
        "collection": "Quran",
        "collection_ar": "القرآن الكريم",
        "compiler": "",
        "compiler_ar": "",
        "locator": "Quran 4:1",
        "record_number": "4:1",
        "source_url": "https://quran.com/4/1",
        "arabic_anchor_text": (
            "خلقكم من نفس واحدة وخلق منها زوجها "
            "وبث منهما رجالا كثيرا ونساء"
        ),
        "proposed_origin_classification": "quran_explicit",
        "authority_tier_candidate": "QURAN_REFERENCE_ANCHOR",
        "aliases": ["القرآن", "سورة النساء", "Quran", "An-Nisa"],
    },
    {
        "source_candidate_id": "SRC-BUKHARI-3331",
        "source_kind": "HADITH_COLLECTION_RECORD",
        "collection": "Sahih al-Bukhari",
        "collection_ar": "صحيح البخاري",
        "compiler": "Muhammad ibn Ismail al-Bukhari",
        "compiler_ar": "محمد بن إسماعيل البخاري",
        "locator": "Sahih al-Bukhari 3331",
        "record_number": "3331",
        "source_url": "https://sunnah.com/bukhari:3331",
        "arabic_anchor_text": (
            "استوصوا بالنساء فإن المرأة خلقت من ضلع "
            "وإن أعوج شيء في الضلع أعلاه"
        ),
        "proposed_origin_classification": "authentic_sunnah",
        "authority_tier_candidate": "SAHIH_COLLECTION_RECORD",
        "aliases": ["البخاري", "صحيح البخاري", "Bukhari", "Sahih al-Bukhari"],
    },
    {
        "source_candidate_id": "SRC-MUSLIM-1468A",
        "source_kind": "HADITH_COLLECTION_RECORD",
        "collection": "Sahih Muslim",
        "collection_ar": "صحيح مسلم",
        "compiler": "Muslim ibn al-Hajjaj",
        "compiler_ar": "مسلم بن الحجاج",
        "locator": "Sahih Muslim 1468a",
        "record_number": "1468",
        "source_url": "https://sunnah.com/muslim:1468a",
        "arabic_anchor_text": (
            "واستوصوا بالنساء فإن المرأة خلقت من ضلع "
            "وإن أعوج شيء في الضلع أعلاه"
        ),
        "proposed_origin_classification": "authentic_sunnah",
        "authority_tier_candidate": "SAHIH_COLLECTION_RECORD",
        "aliases": ["مسلم", "صحيح مسلم", "Muslim", "Sahih Muslim"],
    },
)

EVENT_PROPOSALS = (
    {
        "event_id": "EV-ADAM-001",
        "title": "وجود الله قبل الخلق",
        "proposed_disposition": "include_assertive",
        "source_candidate_ids": ["SRC-BUKHARI-3191"],
        "claim_layers": [
            {
                "claim": "كان الله ولم يكن شيء غيره",
                "treatment": "assertive_candidate",
                "support": ["SRC-BUKHARI-3191"],
            }
        ],
        "scope_limitations": [
            "لا يضاف ترتيب تفصيلي للمخلوقات غير الوارد في النص",
        ],
    },
    {
        "event_id": "EV-ADAM-002",
        "title": "العرش على الماء",
        "proposed_disposition": "include_assertive",
        "source_candidate_ids": [
            "SRC-BUKHARI-3191", "SRC-MUSLIM-2653B",
        ],
        "claim_layers": [
            {
                "claim": "كان العرش على الماء قبل خلق السماوات والأرض",
                "treatment": "assertive_candidate",
                "support": ["SRC-BUKHARI-3191", "SRC-MUSLIM-2653B"],
            }
        ],
        "scope_limitations": [
            "لا يجزم من هذه الحزمة وحدها بترتيب خلق العرش والقلم",
        ],
    },
    {
        "event_id": "EV-ADAM-003",
        "title": "القلم وكتابة المقادير",
        "proposed_disposition": "include_qualified",
        "source_candidate_ids": [
            "SRC-MUSLIM-2653B", "SRC-ABUDAWUD-4700",
            "SRC-TIRMIDHI-2155",
        ],
        "claim_layers": [
            {
                "claim": "كتبت مقادير الخلائق قبل خلق السماوات والأرض",
                "treatment": "assertive_candidate",
                "support": ["SRC-MUSLIM-2653B"],
            },
            {
                "claim": "أمر القلم بكتابة المقادير",
                "treatment": "assertive_candidate_pending_authority_review",
                "support": ["SRC-ABUDAWUD-4700", "SRC-TIRMIDHI-2155"],
            },
            {
                "claim": "القلم أول المخلوقات على الإطلاق",
                "treatment": "chronology_interpretation_review_required",
                "support": ["SRC-ABUDAWUD-4700", "SRC-TIRMIDHI-2155"],
            },
        ],
        "scope_limitations": [
            "تفصل دلالة الحديث عن مسألة ترتيب العرش والماء والقلم",
            "لا يحسم التعارض الظاهري آليا",
        ],
    },
    {
        "event_id": "EV-ADAM-005",
        "title": "خلق الملائكة",
        "proposed_disposition": "include_assertive",
        "source_candidate_ids": ["SRC-MUSLIM-2996"],
        "claim_layers": [
            {
                "claim": "خلقت الملائكة من نور",
                "treatment": "assertive_candidate",
                "support": ["SRC-MUSLIM-2996"],
            }
        ],
        "scope_limitations": [
            "لا يحدد النص زمن خلق الملائكة تفصيلا بالنسبة إلى العرش والقلم",
        ],
    },
    {
        "event_id": "EV-ADAM-007",
        "title": "وجود إبليس قبل خلق آدم",
        "proposed_disposition": "include_qualified",
        "source_candidate_ids": [
            "SRC-QURAN-002-034", "SRC-QURAN-018-050",
            "SRC-QURAN-015-027",
        ],
        "claim_layers": [
            {
                "claim": "إبليس كان من الجن وكان حاضرا عند أمر السجود لآدم",
                "treatment": "assertive_candidate",
                "support": ["SRC-QURAN-002-034", "SRC-QURAN-018-050"],
            },
            {
                "claim": "إبليس بعينه كان موجودا قبل بدء خلق آدم",
                "treatment": "supported_synthesis_human_review_required",
                "support": ["SRC-QURAN-018-050", "SRC-QURAN-015-027"],
            },
        ],
        "scope_limitations": [
            "خلق الجان قبل الإنسان لا يثبت وحده تاريخ كل فرد من الجن",
            "لا تضاف أخبار اسم إبليس أو منزلته قبل المعصية بلا مصدر مستقل",
        ],
    },
    {
        "event_id": "EV-ADAM-021",
        "title": "أطوار الطين والحمأ والصلصال",
        "proposed_disposition": "include_qualified",
        "source_candidate_ids": [
            "SRC-QURAN-003-059", "SRC-QURAN-015-026",
            "SRC-QURAN-037-011", "SRC-QURAN-055-014",
            "SRC-QURAN-038-071",
        ],
        "claim_layers": [
            {
                "claim": "وصف القرآن مادة خلق آدم بالتراب والطين اللازب والحمإ والصلصال",
                "treatment": "assertive_candidate",
                "support": [
                    "SRC-QURAN-003-059", "SRC-QURAN-015-026",
                    "SRC-QURAN-037-011", "SRC-QURAN-055-014",
                    "SRC-QURAN-038-071",
                ],
            },
            {
                "claim": "هذه الأوصاف مراحل زمنية مرتبة بهذا التسلسل",
                "treatment": "scholarly_interpretation_review_required",
                "support": [
                    "SRC-QURAN-003-059", "SRC-QURAN-015-026",
                    "SRC-QURAN-037-011", "SRC-QURAN-055-014",
                    "SRC-QURAN-038-071",
                ],
            },
        ],
        "scope_limitations": [
            "القرآن يثبت الأوصاف ولا ينص في هذه المواضع على مدة كل طور",
            "أي ترتيب بصري أو زمني يحتاج قرارا تفسيريا بشريا",
        ],
    },
    {
        "event_id": "EV-ADAM-023",
        "title": "بقاء جسد آدم قبل نفخ الروح",
        "proposed_disposition": "include_assertive",
        "source_candidate_ids": ["SRC-MUSLIM-2611A"],
        "claim_layers": [
            {
                "claim": "صور الله آدم وتركه مدة شاءها قبل تمام حاله",
                "treatment": "assertive_candidate",
                "support": ["SRC-MUSLIM-2611A"],
            }
        ],
        "scope_limitations": [
            "لا يحدد النص مقدار المدة",
            "لا تضاف تفاصيل حركة الروح من هذا الحديث",
        ],
    },
    {
        "event_id": "EV-ADAM-024",
        "title": "مرور إبليس بجسد آدم",
        "proposed_disposition": "include_assertive",
        "source_candidate_ids": ["SRC-MUSLIM-2611A"],
        "claim_layers": [
            {
                "claim": "جعل إبليس يطيف بآدم وينظر ما هو قبل نفخ الروح",
                "treatment": "assertive_candidate",
                "support": ["SRC-MUSLIM-2611A"],
            }
        ],
        "scope_limitations": [
            "لا يضاف حوار أو فعل لم يذكره الحديث",
            "الوصف البصري يبقى خاضعا لسياسة الغيب وعدم تصوير الأنبياء",
        ],
    },
    {
        "event_id": "EV-ADAM-032",
        "title": "طول آدم وصفته الأولى",
        "proposed_disposition": "include_assertive",
        "source_candidate_ids": [
            "SRC-BUKHARI-3326", "SRC-MUSLIM-2841",
        ],
        "claim_layers": [
            {
                "claim": "خلق آدم وطوله ستون ذراعا",
                "treatment": "assertive_candidate",
                "support": ["SRC-BUKHARI-3326", "SRC-MUSLIM-2841"],
            }
        ],
        "scope_limitations": [
            "لا يحول القياس إلى تصوير مرئي للنبي آدم",
            "تفاصيل معنى الصورة تبحث مستقلة ولا توسع هنا",
        ],
    },
    {
        "event_id": "EV-ADAM-033",
        "title": "تعليم آدم تحية السلام",
        "proposed_disposition": "include_assertive",
        "source_candidate_ids": [
            "SRC-BUKHARI-3326", "SRC-MUSLIM-2841",
        ],
        "claim_layers": [
            {
                "claim": "أمر آدم أن يسلم على الملائكة فكانت تحيته وتحية ذريته",
                "treatment": "assertive_candidate",
                "support": ["SRC-BUKHARI-3326", "SRC-MUSLIM-2841"],
            }
        ],
        "scope_limitations": [
            "ينقل الحوار بقدر النص دون إضافات درامية",
        ],
    },
    {
        "event_id": "EV-ADAM-042",
        "title": "إظهار فضل آدم بالعلم",
        "proposed_disposition": "include_qualified",
        "source_candidate_ids": ["SRC-QURAN-002-031-033"],
        "claim_layers": [
            {
                "claim": "علم الله آدم الأسماء وأنبأ آدم الملائكة بها",
                "treatment": "assertive_candidate",
                "support": ["SRC-QURAN-002-031-033"],
            },
            {
                "claim": "كان هذا إظهارا لفضل آدم بالعلم",
                "treatment": "scholarly_interpretation_review_required",
                "support": ["SRC-QURAN-002-031-033"],
            },
        ],
        "scope_limitations": [
            "لا يجزم بتعيين ماهية جميع الأسماء دون تفسير معتمد",
            "ربط العلم بالاستخلاف استنباط يحتاج نسبة واضحة",
        ],
    },
    {
        "event_id": "EV-ADAM-060",
        "title": "ميثاق بني آدم",
        "proposed_disposition": "include_assertive",
        "source_candidate_ids": ["SRC-QURAN-007-172"],
        "claim_layers": [
            {
                "claim": "أخذ الله من بني آدم ذريتهم وأشهدهم على ربوبيته",
                "treatment": "assertive_candidate",
                "support": ["SRC-QURAN-007-172"],
            }
        ],
        "scope_limitations": [
            "لا يعين النص هنا موضع الحدث الزمني بالنسبة إلى بقية قصة آدم",
            "لا تدمج تلقائيا جميع روايات الميثاق في واقعة واحدة",
        ],
    },
    {
        "event_id": "EV-ADAM-061",
        "title": "استخراج ذرية آدم من ظهره",
        "proposed_disposition": "include_qualified",
        "source_candidate_ids": [
            "SRC-QURAN-007-172", "SRC-TIRMIDHI-3076",
        ],
        "claim_layers": [
            {
                "claim": "أخذت ذرية بني آدم من ظهورهم",
                "treatment": "assertive_candidate",
                "support": ["SRC-QURAN-007-172"],
            },
            {
                "claim": "مسح ظهر آدم وسقطت منه كل نسمة من ذريته",
                "treatment": "hadith_authority_review_required",
                "support": ["SRC-TIRMIDHI-3076"],
            },
        ],
        "scope_limitations": [
            "لا يساوى آليا بين كل تفاصيل الحديث ودلالة آية الأعراف",
            "تفاصيل داود والعمر خارج نطاق الحدث ما لم تعتمد مستقلة",
        ],
    },
    {
        "event_id": "EV-ADAM-070",
        "title": "خلق زوج آدم",
        "proposed_disposition": "include_qualified",
        "source_candidate_ids": [
            "SRC-QURAN-004-001", "SRC-BUKHARI-3331",
            "SRC-MUSLIM-1468A",
        ],
        "claim_layers": [
            {
                "claim": "خلق الله من النفس الواحدة زوجها",
                "treatment": "assertive_candidate",
                "support": ["SRC-QURAN-004-001"],
            },
            {
                "claim": "المرأة خلقت من ضلع",
                "treatment": "assertive_candidate",
                "support": ["SRC-BUKHARI-3331", "SRC-MUSLIM-1468A"],
            },
            {
                "claim": "زوج آدم المقصودة هي حواء وأنها خلقت من ضلع آدم",
                "treatment": "supported_synthesis_human_review_required",
                "support": [
                    "SRC-QURAN-004-001", "SRC-BUKHARI-3331",
                    "SRC-MUSLIM-1468A",
                ],
            },
        ],
        "scope_limitations": [
            "لا يثبت من هذه النصوص تعيين الضلع الأيسر أو وقت النوم",
            "تفاصيل الحوار والتسمية تبقى ضمن قرار EV-ADAM-071",
        ],
    },
)


class ExternalSourceCandidateError(ValueError):
    pass


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ExternalSourceCandidateError(f"Invalid JSON: {path}") from exc


def build_policy() -> dict:
    policy = {
        "schema_version": POLICY_SCHEMA,
        "status": "EXTERNAL_SOURCE_CANDIDATE_POLICY_ACTIVE",
        "episode_id": "episode-001-adam",
        "research_date": RESEARCH_DATE,
        "allowed_candidate_kinds": [
            "QURAN_VERSE",
            "QURAN_VERSE_RANGE",
            "HADITH_COLLECTION_RECORD",
        ],
        "candidate_record_schema": RECORD_SCHEMA,
        "rules": {
            "reference_anchor": (
                "Arabic anchor text is a research locator aid, not a "
                "human-compared source excerpt."
            ),
            "sahih_collection_record": (
                "Collection identity is recorded, but authentication_verified "
                "remains false until a qualified human records the decision."
            ),
            "sunan_record": (
                "Requires explicit human authentication-authority review."
            ),
            "quran_anchor": (
                "Requires human comparison against an authorized Mushaf source "
                "before source_verified can become true."
            ),
            "event_disposition": (
                "All proposed dispositions are candidates and never human decisions."
            ),
        },
        "prohibitions": [
            "automatic hadith grading",
            "automatic source authentication",
            "automatic source-origin classification",
            "automatic narration approval",
            "treating a research anchor as a verified exact excerpt",
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
        "adam_external_source_policy_" + canonical_sha256(policy)[:16]
    )
    validate_policy(policy)
    return policy


def build_catalog(policy: Mapping[str, object]) -> dict:
    records = []
    for base in SOURCE_RECORDS:
        record = dict(base)
        record.update({
            "research_date": RESEARCH_DATE,
            "research_method": "ASSISTED_WEB_RESEARCH",
            "arabic_anchor_form": "NORMALIZED_REFERENCE_ANCHOR",
            "arabic_anchor_sha256": text_sha256(record["arabic_anchor_text"]),
            "source_material_sha256": "",
            "remote_content_archived": False,
            "human_compared_to_source": False,
            "source_verified": False,
            "authentication_verified": False,
            "origin_classification_verified": False,
            "human_decision": False,
            "approved_for_event_binding": False,
            "policy_id": policy["policy_id"],
            "policy_sha256": canonical_sha256(policy),
        })
        record["candidate_record_id"] = (
            "external_source_" + canonical_sha256(record)[:16]
        )
        records.append(record)
    catalog = {
        "schema_version": CATALOG_SCHEMA,
        "status": STATUS,
        "episode_id": "episode-001-adam",
        "research_date": RESEARCH_DATE,
        "source_candidate_count": len(records),
        "quran_candidate_count": sum(
            item["source_kind"].startswith("QURAN") for item in records
        ),
        "hadith_candidate_count": sum(
            item["source_kind"] == "HADITH_COLLECTION_RECORD"
            for item in records
        ),
        "source_candidates": records,
        "policy_id": policy["policy_id"],
        "policy_sha256": canonical_sha256(policy),
        "human_approval": False,
        "source_verification_complete": False,
        "approved_evidence_package_complete": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    catalog["catalog_id"] = (
        "adam_external_source_catalog_" + canonical_sha256(catalog)[:16]
    )
    validate_catalog(catalog)
    return catalog


def build_event_pack(
    catalog: Mapping[str, object], policy: Mapping[str, object]
) -> dict:
    source_index = {
        item["source_candidate_id"]: item
        for item in catalog["source_candidates"]
    }
    events = []
    link_count = 0
    for proposal in EVENT_PROPOSALS:
        item = dict(proposal)
        links = []
        for source_id in proposal["source_candidate_ids"]:
            source = source_index[source_id]
            links.append({
                "source_candidate_id": source_id,
                "candidate_record_id": source["candidate_record_id"],
                "locator": source["locator"],
                "source_url": source["source_url"],
                "arabic_anchor_sha256": source["arabic_anchor_sha256"],
                "source_candidate_sha256": canonical_sha256(source),
                "source_verified": False,
                "human_decision": False,
            })
        link_count += len(links)
        item.update({
            "source_links": links,
            "source_candidate_count": len(links),
            "human_decision": False,
            "event_approved": False,
            "source_verification_complete": False,
            "binding_ready": False,
        })
        events.append(item)
    pack = {
        "schema_version": PACK_SCHEMA,
        "status": STATUS,
        "episode_id": "episode-001-adam",
        "catalog_id": catalog["catalog_id"],
        "catalog_sha256": canonical_sha256(catalog),
        "policy_id": policy["policy_id"],
        "policy_sha256": canonical_sha256(policy),
        "event_count": len(events),
        "event_ids": [item["event_id"] for item in events],
        "event_source_link_count": link_count,
        "proposed_disposition_counts": dict(sorted(Counter(
            item["proposed_disposition"] for item in events
        ).items())),
        "events": events,
        "human_approval": False,
        "source_verification_complete": False,
        "full_episode_adjudication_complete": False,
        "approved_evidence_package_complete": False,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    pack["pack_id"] = (
        "adam_external_event_source_pack_" + canonical_sha256(pack)[:16]
    )
    validate_event_pack(pack, catalog)
    return pack


def build_review_template(
    pack: Mapping[str, object], policy: Mapping[str, object]
) -> dict:
    review = {
        "schema_version": REVIEW_SCHEMA,
        "status": "TEMPLATE_NOT_APPROVED",
        "episode_id": "episode-001-adam",
        "pack_id": pack["pack_id"],
        "pack_sha256": canonical_sha256(pack),
        "policy_id": policy["policy_id"],
        "policy_sha256": canonical_sha256(policy),
        "event_count": pack["event_count"],
        "decisions": [
            {
                "event_id": item["event_id"],
                "proposed_disposition": item["proposed_disposition"],
                "approved_source_candidate_ids": [],
                "rejected_source_candidate_ids": [],
                "source_verification_complete": False,
                "approved": False,
                "human_decision": False,
                "reviewer_notes": "",
            }
            for item in pack["events"]
        ],
        "approved_by": "",
        "approved_at": "",
        "human_approval": False,
        "full_episode_adjudication_complete": False,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    validate_review_template(review)
    return review


def build_candidate_records(
    pack: Mapping[str, object], catalog: Mapping[str, object],
    policy: Mapping[str, object],
) -> dict[str, dict]:
    source_index = {
        item["source_candidate_id"]: item
        for item in catalog["source_candidates"]
    }
    records = {}
    for event in pack["events"]:
        for source_id in event["source_candidate_ids"]:
            source = source_index[source_id]
            record = {
                "schema_version": RECORD_SCHEMA,
                "status": "CANDIDATE_NOT_VERIFIED",
                "episode_id": "episode-001-adam",
                "event_id": event["event_id"],
                "event_title": event["title"],
                "proposed_event_disposition": event["proposed_disposition"],
                "source_candidate_id": source_id,
                "source_kind": source["source_kind"],
                "source_title": source["collection"],
                "source_title_ar": source["collection_ar"],
                "compiler": source["compiler"],
                "compiler_ar": source["compiler_ar"],
                "volume_page_or_record_number": source["locator"],
                "reference_url": source["source_url"],
                "research_anchor_text": source["arabic_anchor_text"],
                "research_anchor_sha256": source["arabic_anchor_sha256"],
                "exact_excerpt": "",
                "context_before_after": "",
                "source_material_sha256": "",
                "exact_excerpt_sha256": "",
                "verification_method": "",
                "authentication_authority": "",
                "authentication_result": "",
                "authentication_locator": "",
                "proposed_origin_classification": source[
                    "proposed_origin_classification"
                ],
                "origin_classification": "unresolved",
                "classification_notes": "",
                "uncertainties": list(event["scope_limitations"]),
                "human_compared_to_source": False,
                "source_verified": False,
                "authentication_verified": False,
                "origin_classification_verified": False,
                "human_decision": False,
                "approved_for_event_binding": False,
                "verified_by": "",
                "verified_at": "",
                "policy_id": policy["policy_id"],
                "policy_sha256": canonical_sha256(policy),
                "opens_evidence_gate": False,
                "evidence_gate_status": GATE,
                "automatic_evidence_approval": AUTO_APPROVAL,
                "live_provider_execution": LIVE_EXECUTION,
            }
            record_id = (
                event["event_id"].lower().replace("-", "_")
                + "_external_"
                + canonical_sha256(record)[:16]
            )
            record["external_candidate_record_id"] = record_id
            records[record_id] = record
    return records


def _normalise(value: str) -> str:
    return " ".join(value.lower().replace("`", "").split())


def _candidate_match_score(
    local_record: Mapping[str, object],
    source: Mapping[str, object],
) -> tuple[int, list[str]]:
    score = 0
    reasons = []
    detected_numbers = {
        str(value).lower()
        for value in local_record.get("detected_numbers", [])
    }
    detected_names = " ".join(
        str(value) for value in local_record.get("detected_source_names", [])
    )
    excerpt = str(local_record.get("candidate_excerpt", ""))
    haystack = _normalise(detected_names + " " + excerpt)
    record_number = str(source["record_number"]).lower()
    number_variants = {record_number, record_number.rstrip("ab")}
    if detected_numbers & number_variants:
        score += 65
        reasons.append("record_number_match")
    elif any(number in haystack for number in number_variants):
        score += 45
        reasons.append("record_number_in_excerpt")
    alias_hits = [
        alias for alias in source["aliases"]
        if _normalise(alias) in haystack
    ]
    if alias_hits:
        score += 35
        reasons.append("source_alias_match:" + "|".join(alias_hits[:3]))
    if str(source["locator"]).lower() in haystack:
        score += 30
        reasons.append("full_locator_match")
    anchor_tokens = {
        token for token in _normalise(source["arabic_anchor_text"]).split()
        if len(token) >= 4
    }
    excerpt_tokens = set(_normalise(excerpt).split())
    overlap = len(anchor_tokens & excerpt_tokens)
    if overlap:
        score += min(overlap * 3, 24)
        reasons.append(f"anchor_token_overlap:{overlap}")
    return score, reasons


def build_auto_match_ledger(
    *, execution_report_root: Path, pack: Mapping[str, object],
    catalog: Mapping[str, object],
) -> dict:
    execution_report_root = Path(execution_report_root)
    execution_path = execution_report_root / "source-verification-execution-v1.json"
    execution = read_json(execution_path)
    if not isinstance(execution, Mapping):
        raise ExternalSourceCandidateError("Execution report must be an object.")
    if execution.get("schema_version") != (
        "siraj-non-quran-source-verification-execution-v1"
    ):
        raise ExternalSourceCandidateError("Unexpected execution schema.")
    source_index = {
        item["source_candidate_id"]: item
        for item in catalog["source_candidates"]
    }
    event_sources = {
        item["event_id"]: item["source_candidate_ids"]
        for item in pack["events"]
    }
    local_paths = sorted(
        (execution_report_root / "verification-records").rglob("*.json")
    )
    if len(local_paths) != execution.get("record_template_count"):
        raise ExternalSourceCandidateError(
            "Local verification-record count does not match execution report."
        )
    matches = []
    confidence_counts = Counter()
    records_with_high_match = set()
    for path in local_paths:
        record = read_json(path)
        if not isinstance(record, Mapping):
            raise ExternalSourceCandidateError("Local record must be an object.")
        event_id = str(record.get("event_id", ""))
        if event_id not in event_sources:
            raise ExternalSourceCandidateError(
                f"Unexpected local record event: {event_id}"
            )
        ranked = []
        for source_id in event_sources[event_id]:
            score, reasons = _candidate_match_score(record, source_index[source_id])
            ranked.append({
                "source_candidate_id": source_id,
                "score": score,
                "match_reasons": reasons,
            })
        ranked.sort(key=lambda item: (-item["score"], item["source_candidate_id"]))
        best_score = ranked[0]["score"] if ranked else 0
        confidence = (
            "HIGH" if best_score >= 80
            else "MEDIUM" if best_score >= 45
            else "EVENT_SCOPE_ONLY"
        )
        confidence_counts[confidence] += 1
        if confidence == "HIGH":
            records_with_high_match.add(record.get("record_template_id"))
        matches.append({
            "local_record_template_id": record.get("record_template_id"),
            "event_id": event_id,
            "candidate_id": record.get("candidate_id"),
            "candidate_path": record.get("candidate_path"),
            "candidate_excerpt_sha256": record.get(
                "candidate_excerpt_sha256"
            ),
            "confidence": confidence,
            "best_score": best_score,
            "ranked_source_candidates": ranked,
            "automatic_source_verification": False,
            "automatic_authentication": False,
            "human_review_required": True,
        })
    ledger = {
        "schema_version": MATCH_SCHEMA,
        "status": "AUTO_MATCH_READY_HUMAN_REVIEW_REQUIRED",
        "episode_id": "episode-001-adam",
        "execution_id": execution["execution_id"],
        "execution_sha256": canonical_sha256(execution),
        "pack_id": pack["pack_id"],
        "pack_sha256": canonical_sha256(pack),
        "local_record_count": len(matches),
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "high_confidence_record_count": len(records_with_high_match),
        "matches": matches,
        "source_verification_complete": False,
        "human_approval": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    ledger["match_ledger_id"] = (
        "adam_external_source_match_" + canonical_sha256(ledger)[:16]
    )
    validate_match_ledger(ledger)
    return ledger


def validate_policy(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != POLICY_SCHEMA:
        raise ExternalSourceCandidateError("Unexpected policy schema.")
    if "automatic hadith grading" not in data.get("prohibitions", []):
        raise ExternalSourceCandidateError("Hadith-grading prohibition missing.")
    if data.get("source_verification_complete") is not False:
        raise ExternalSourceCandidateError("Policy cannot complete verification.")
    _validate_guards(data)


def validate_catalog(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != CATALOG_SCHEMA or data.get("status") != STATUS:
        raise ExternalSourceCandidateError("Unexpected catalog schema/status.")
    records = data.get("source_candidates")
    if not isinstance(records, list) or len(records) != 22:
        raise ExternalSourceCandidateError("Expected exactly 22 source candidates.")
    ids = [item.get("source_candidate_id") for item in records]
    if len(ids) != len(set(ids)):
        raise ExternalSourceCandidateError("Source candidate ids are duplicated.")
    if data.get("quran_candidate_count") != 11:
        raise ExternalSourceCandidateError("Expected eleven Quran candidates.")
    if data.get("hadith_candidate_count") != 11:
        raise ExternalSourceCandidateError("Expected eleven hadith candidates.")
    for item in records:
        anchor = item.get("arabic_anchor_text")
        if not isinstance(anchor, str) or not anchor.strip():
            raise ExternalSourceCandidateError("Research anchor missing.")
        if text_sha256(anchor) != item.get("arabic_anchor_sha256"):
            raise ExternalSourceCandidateError("Research anchor checksum mismatch.")
        if item.get("human_compared_to_source") is not False:
            raise ExternalSourceCandidateError("Candidate cannot claim comparison.")
        if item.get("source_verified") is not False:
            raise ExternalSourceCandidateError("Candidate cannot claim verification.")
        if item.get("authentication_verified") is not False:
            raise ExternalSourceCandidateError("Candidate cannot claim authentication.")
        if item.get("origin_classification_verified") is not False:
            raise ExternalSourceCandidateError("Candidate cannot claim origin verification.")
        if item.get("approved_for_event_binding") is not False:
            raise ExternalSourceCandidateError("Candidate cannot be binding-approved.")
        if item.get("source_material_sha256"):
            raise ExternalSourceCandidateError("Remote source hash must remain blank.")
    _validate_guards(data)


def validate_event_pack(
    data: Mapping[str, object], catalog: Mapping[str, object]
) -> None:
    if data.get("schema_version") != PACK_SCHEMA or data.get("status") != STATUS:
        raise ExternalSourceCandidateError("Unexpected event-pack schema/status.")
    if tuple(data.get("event_ids", ())) != FACTUAL_EVENTS:
        raise ExternalSourceCandidateError("Event-pack coverage changed.")
    events = data.get("events")
    if not isinstance(events, list) or len(events) != 14:
        raise ExternalSourceCandidateError("Event pack must cover fourteen events.")
    if data.get("event_source_link_count") != 28:
        raise ExternalSourceCandidateError("Expected 28 event/source links.")
    source_ids = {
        item["source_candidate_id"]
        for item in catalog["source_candidates"]
    }
    for event in events:
        if event.get("human_decision") is not False:
            raise ExternalSourceCandidateError("Human decision cannot be prefilled.")
        if event.get("event_approved") is not False:
            raise ExternalSourceCandidateError("Event cannot be preapproved.")
        if event.get("source_verification_complete") is not False:
            raise ExternalSourceCandidateError("Verification cannot be pre-complete.")
        if event.get("binding_ready") is not False:
            raise ExternalSourceCandidateError("Event cannot be binding-ready.")
        if event.get("proposed_disposition") not in {
            "include_assertive", "include_qualified"
        }:
            raise ExternalSourceCandidateError("Unexpected proposed disposition.")
        for source_id in event.get("source_candidate_ids", []):
            if source_id not in source_ids:
                raise ExternalSourceCandidateError("Unknown source link.")
    if data.get("proposed_disposition_counts") != {
        "include_assertive": 8,
        "include_qualified": 6,
    }:
        raise ExternalSourceCandidateError("Disposition counts changed.")
    if data.get("opens_evidence_gate") is not False:
        raise ExternalSourceCandidateError("Event pack cannot open the gate.")
    _validate_guards(data)


def validate_review_template(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != REVIEW_SCHEMA:
        raise ExternalSourceCandidateError("Unexpected review schema.")
    if data.get("status") != "TEMPLATE_NOT_APPROVED":
        raise ExternalSourceCandidateError("Review template cannot be approved.")
    decisions = data.get("decisions")
    if not isinstance(decisions, list) or len(decisions) != 14:
        raise ExternalSourceCandidateError("Review must cover fourteen events.")
    for item in decisions:
        if item.get("approved_source_candidate_ids"):
            raise ExternalSourceCandidateError("Approved-source list must be blank.")
        if item.get("rejected_source_candidate_ids"):
            raise ExternalSourceCandidateError("Rejected-source list must be blank.")
        if item.get("source_verification_complete") is not False:
            raise ExternalSourceCandidateError("Verification cannot be pre-complete.")
        if item.get("approved") is not False:
            raise ExternalSourceCandidateError("Review cannot be preapproved.")
        if item.get("human_decision") is not False:
            raise ExternalSourceCandidateError("Human decision cannot be prefilled.")
    if data.get("approved_by") or data.get("approved_at"):
        raise ExternalSourceCandidateError("Reviewer metadata must be blank.")
    _validate_guards(data)


def validate_candidate_record(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != RECORD_SCHEMA:
        raise ExternalSourceCandidateError("Unexpected candidate-record schema.")
    if data.get("status") != "CANDIDATE_NOT_VERIFIED":
        raise ExternalSourceCandidateError("Candidate record cannot be verified.")
    if not re.fullmatch(r"EV-ADAM-\d{3}", str(data.get("event_id", ""))):
        raise ExternalSourceCandidateError("Invalid event id.")
    if text_sha256(str(data.get("research_anchor_text", ""))) != data.get(
        "research_anchor_sha256"
    ):
        raise ExternalSourceCandidateError("Candidate anchor checksum mismatch.")
    blank_fields = (
        "exact_excerpt", "context_before_after", "source_material_sha256",
        "exact_excerpt_sha256", "verification_method",
        "authentication_authority", "authentication_result",
        "authentication_locator", "classification_notes",
        "verified_by", "verified_at",
    )
    if any(data.get(field) for field in blank_fields):
        raise ExternalSourceCandidateError("Verification fields must remain blank.")
    false_fields = (
        "human_compared_to_source", "source_verified",
        "authentication_verified", "origin_classification_verified",
        "human_decision", "approved_for_event_binding", "opens_evidence_gate",
    )
    if any(data.get(field) is not False for field in false_fields):
        raise ExternalSourceCandidateError("Candidate cannot claim verification/approval.")
    if data.get("origin_classification") != "unresolved":
        raise ExternalSourceCandidateError("Origin must remain unresolved.")
    _validate_guards(data)


def validate_match_ledger(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != MATCH_SCHEMA:
        raise ExternalSourceCandidateError("Unexpected match-ledger schema.")
    matches = data.get("matches")
    if not isinstance(matches, list) or not matches:
        raise ExternalSourceCandidateError("Match ledger is empty.")
    if data.get("local_record_count") != len(matches):
        raise ExternalSourceCandidateError("Match-ledger count mismatch.")
    for item in matches:
        if item.get("confidence") not in {
            "HIGH", "MEDIUM", "EVENT_SCOPE_ONLY"
        }:
            raise ExternalSourceCandidateError("Unexpected match confidence.")
        if item.get("automatic_source_verification") is not False:
            raise ExternalSourceCandidateError("Auto-match cannot verify sources.")
        if item.get("automatic_authentication") is not False:
            raise ExternalSourceCandidateError("Auto-match cannot authenticate.")
        if item.get("human_review_required") is not True:
            raise ExternalSourceCandidateError("Human review must remain required.")
    _validate_guards(data)


def _validate_guards(data: Mapping[str, object]) -> None:
    if data.get("human_approval") not in (None, False):
        raise ExternalSourceCandidateError("Artifact cannot claim human approval.")
    if data.get("evidence_gate_status") != GATE:
        raise ExternalSourceCandidateError("Evidence gate must remain withheld.")
    if data.get("automatic_evidence_approval") != AUTO_APPROVAL:
        raise ExternalSourceCandidateError("Automatic approval must remain forbidden.")
    if data.get("live_provider_execution") != LIVE_EXECUTION:
        raise ExternalSourceCandidateError("Provider execution must remain blocked.")


def write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_local_outputs(
    *, output_root: Path, catalog: Mapping[str, object],
    pack: Mapping[str, object], policy: Mapping[str, object],
    review: Mapping[str, object], candidate_records: Mapping[str, Mapping[str, object]],
    match_ledger: Mapping[str, object],
) -> dict[str, Path]:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    outputs = {
        "catalog": output_root / "external-source-candidate-catalog-v1.json",
        "pack": output_root / "external-event-source-candidate-pack-v1.json",
        "policy": output_root / "external-source-candidate-policy-v1.json",
        "review": output_root / "external-source-human-review-v1.template.json",
        "matches": output_root / "external-source-auto-match-ledger-v1.json",
        "source_csv": output_root / "source-candidate-catalog.csv",
        "event_csv": output_root / "event-source-link-coverage.csv",
        "match_csv": output_root / "local-record-source-matches.csv",
        "summary": output_root / "README.md",
    }
    write_json(outputs["catalog"], catalog)
    write_json(outputs["pack"], pack)
    write_json(outputs["policy"], policy)
    write_json(outputs["review"], review)
    write_json(outputs["matches"], match_ledger)

    record_root = output_root / "candidate-records"
    for record_id, record in sorted(candidate_records.items()):
        validate_candidate_record(record)
        write_json(
            record_root / record["event_id"] / f"{record_id}.json",
            record,
        )

    source_fields = (
        "source_candidate_id", "source_kind", "collection",
        "locator", "source_url", "proposed_origin_classification",
        "authority_tier_candidate", "source_verified",
    )
    with outputs["source_csv"].open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=source_fields)
        writer.writeheader()
        for source in catalog["source_candidates"]:
            writer.writerow({key: source[key] for key in source_fields})

    event_fields = (
        "event_id", "title", "proposed_disposition",
        "source_candidate_count", "source_candidate_ids",
    )
    with outputs["event_csv"].open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=event_fields)
        writer.writeheader()
        for event in pack["events"]:
            writer.writerow({
                "event_id": event["event_id"],
                "title": event["title"],
                "proposed_disposition": event["proposed_disposition"],
                "source_candidate_count": event["source_candidate_count"],
                "source_candidate_ids": ";".join(event["source_candidate_ids"]),
            })

    match_fields = (
        "local_record_template_id", "event_id", "candidate_id",
        "confidence", "best_score", "top_source_candidate_id",
    )
    with outputs["match_csv"].open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=match_fields)
        writer.writeheader()
        for item in match_ledger["matches"]:
            ranked = item["ranked_source_candidates"]
            writer.writerow({
                "local_record_template_id": item["local_record_template_id"],
                "event_id": item["event_id"],
                "candidate_id": item["candidate_id"],
                "confidence": item["confidence"],
                "best_score": item["best_score"],
                "top_source_candidate_id": (
                    ranked[0]["source_candidate_id"] if ranked else ""
                ),
            })

    dossier_root = output_root / "event-dossiers"
    dossier_root.mkdir(parents=True, exist_ok=True)
    source_index = {
        item["source_candidate_id"]: item
        for item in catalog["source_candidates"]
    }
    matches_by_event: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for item in match_ledger["matches"]:
        matches_by_event[item["event_id"]].append(item)
    for event in pack["events"]:
        lines = [
            f"# {event['event_id']} — {event['title']}",
            "",
            f"- Proposed disposition: `{event['proposed_disposition']}`",
            f"- Source candidates: {event['source_candidate_count']}",
            f"- Local record matches: {len(matches_by_event[event['event_id']])}",
            "- Human decision: no",
            "- Source verification complete: no",
            "",
            "## Claim layers",
            "",
        ]
        for layer in event["claim_layers"]:
            lines.extend([
                f"- **{layer['treatment']}** — {layer['claim']}",
                f"  - Support: {', '.join(layer['support'])}",
            ])
        lines.extend(["", "## Source candidates", ""])
        for source_id in event["source_candidate_ids"]:
            source = source_index[source_id]
            lines.extend([
                f"### {source_id}",
                "",
                f"- Locator: `{source['locator']}`",
                f"- URL: `{source['source_url']}`",
                f"- Proposed origin: `{source['proposed_origin_classification']}`",
                f"- Human-compared: no",
                f"- Anchor SHA-256: `{source['arabic_anchor_sha256']}`",
                "",
                "```text",
                source["arabic_anchor_text"],
                "```",
                "",
            ])
        lines.extend(["## Scope limitations", ""])
        lines.extend(f"- {value}" for value in event["scope_limitations"])
        (dossier_root / f"{event['event_id']}.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
        )

    outputs["summary"].write_text(
        "# Adam External Source Candidate Pack v1\n\n"
        f"- Source candidates: {catalog['source_candidate_count']}\n"
        f"- Quran candidates: {catalog['quran_candidate_count']}\n"
        f"- Hadith candidates: {catalog['hadith_candidate_count']}\n"
        f"- Factual events covered: {pack['event_count']}\n"
        f"- Event/source links: {pack['event_source_link_count']}\n"
        f"- Local verification records matched: {match_ledger['local_record_count']}\n"
        f"- High-confidence structural matches: "
        f"{match_ledger['high_confidence_record_count']}\n"
        "- Research anchors are not human-compared exact excerpts.\n"
        "- No source was authenticated or approved.\n"
        "- Evidence gate remains withheld.\n",
        encoding="utf-8",
        newline="\n",
    )

    archive = output_root.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(output_root.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(output_root).as_posix())
    outputs["archive"] = archive
    return outputs
