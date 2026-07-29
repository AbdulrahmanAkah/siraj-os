"""Finalize Adam episode script and storyboard as a directorial master candidate."""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Mapping, Sequence

SCRIPT_SCHEMA = "siraj-prestige-cinematic-script-v2.1"
STORYBOARD_SCHEMA = "siraj-detailed-cinematic-storyboard-v2.1"
TRACE_SCHEMA = "siraj-script-storyboard-evidence-trace-v2.1"
APPROVAL_REQUEST_SCHEMA = "siraj-script-storyboard-human-approval-request-v2.1"
PRODUCTION_BRIEF_SCHEMA = "siraj-prestige-production-brief-v2.1"
DIRECTORIAL_AUDIT_SCHEMA = "siraj-storyboard-master-directorial-audit-v2.1"

TIMEZONE = "Asia/Baghdad"
VERSION = "2.1"
LIVE_EXECUTION = "BLOCKED"
PAID_EXECUTION = "BLOCKED"
FORMAT_IDENTITY = "PRESTIGE_HISTORICAL_CINEMATIC_SERIES"
PRODUCTION_PROFILE = "WORLD_CLASS_PRESTIGE_HISTORICAL_CINEMA_V1"
EXPECTED_SEQUENCE_COUNT = 14
EXPECTED_SHOT_COUNT = 70
EXPECTED_TOTAL_SECONDS = 1320
EXPECTED_EVENT_COUNT = 37
EXPECTED_EVIDENCE_COUNT = 57
EXPECTED_QUALIFIED_COUNT = 7

PREDECESSOR_SCRIPT_ID = "adam_prestige_cinematic_script_v2_614069fbe5a5c5f9"
PREDECESSOR_SCRIPT_FINGERPRINT = (
    "614069fbe5a5c5f9baf8d1325a0c96929df30449203e19e835b84506259ff9e7"
)
PREDECESSOR_STORYBOARD_ID = "adam_detailed_cinematic_storyboard_v2_c4722dcdff04d534"
PREDECESSOR_STORYBOARD_FINGERPRINT = (
    "c4722dcdff04d534243e9469fc30510a02ef1e067e9bfafee757d445ac9577b2"
)
PREDECESSOR_TRACE_ID = "adam_script_storyboard_trace_v2_bebe280b14944c2e"

EXACT_COVENANT_VERSE = "﴿أَلَسْتُ بِرَبِّكُمْ قَالُوا بَلَىٰ شَهِدْنَا﴾"
APPROVAL_PHRASE = (
    "أعتمد بشريًا النسخة الإخراجية النهائية للنص السينمائي والستوريبورد "
    "الرئيسي لحلقة آدم بإصدار 2.1 وفق بصمتيهما المحددتين، وأجيز الانتقال "
    "إلى الهوية البصرية الرئيسية والأنيماتيك غير المدفوع دون السماح بأي "
    "تشغيل مدفوع أو مباشر"
)

FORBIDDEN_NARRATION_PHRASES = (
    "وجاءت رواية",
    "وفي خبر يروى",
    "في خبر يُروى",
    "لا نضعها كساعة",
    "حاولت روايات التفسير",
    "أما التفاصيل التي ملأت بها بعض الروايات الفراغ",
    "لا يأتينا إلا من ظلال روايات التفسير",
    "قالوا بلى شهد:",
    "بربكمنا",
)

MASTER_VISUAL_GRAMMAR = {
    "authorship_principle": (
        "Every shot must change dramatic information, emotional pressure, "
        "spatial understanding, or thematic meaning; beauty alone is insufficient."
    ),
    "lens_families": {
        "cosmic_and_mythic_scale": "18–28mm equivalent with disciplined geometry",
        "material_creation": "65–100mm macro with tactile depth falloff",
        "human_consequence": "35–50mm environmental intimacy without literal faces",
        "threat_and_pride": "compressed 70–100mm space or severe axial wides",
    },
    "camera_law": (
        "Camera movement is motivated by discovery, pressure, refusal, or transition; "
        "ornamental drifting is forbidden."
    ),
    "light_law": (
        "Light must have narrative behaviour: reveal, withdraw, divide, or bind. "
        "Unmotivated glow and generic fantasy bloom are forbidden."
    ),
    "colour_arc": [
        "basalt black and cold silver",
        "primordial blue-black and ink gold",
        "earth, clay, rain, and amber",
        "knowledge gold and disciplined pearl",
        "volcanic copper and obsidian",
        "human warmth and covenantal blue",
        "paradise emerald and warning shadow",
        "suspended silver before temptation",
    ],
    "transition_law": (
        "Every transition must carry a shared material, motion vector, sound tail, "
        "or thematic collision into the next sequence."
    ),
    "sound_law": (
        "Sound perspective establishes scale before music; silence is an authored "
        "dramatic event, not an empty gap."
    ),
    "religious_safety": {
        "allah_depiction": "FORBIDDEN",
        "prophet_face_or_body_depiction": "FORBIDDEN",
        "angel_body_depiction": "FORBIDDEN",
        "iblis_body_depiction": "FORBIDDEN",
        "literal_unseen_depiction": "FORBIDDEN",
        "invented_historical_dialogue": "FORBIDDEN",
        "environmental_symbolism": "ALLOWED_NON_ASSERTIVELY",
    },
    "global_rejection_triggers": [
        "generic AI fantasy aesthetic",
        "decorative camera drift without narrative cause",
        "flat slideshow staging",
        "unmotivated lens flare or bloom",
        "literal embodiment of the unseen",
        "visual repetition without escalation",
        "expository on-screen footnote language",
        "stock-footage montage logic",
    ],
}

SEQUENCE_MASTERING = {
    1: {
        "core_emotion": "رهبة الانقسام",
        "continuity_anchor": "الحافة البازلتية والنغمة الشاذة",
        "tension_curve": [2, 5, 8, 9, 6],
        "beats": [
            "إلقاء المشاهد داخل نظام كوني قبل فهمه",
            "إظهار اكتمال الامتثال في حركة واحدة",
            "كشف الاستثناء بوصفه خللًا في النظام",
            "ربط الخلل بمسار التاريخ البشري",
            "سحب الزمن إلى الطين السابق للحكاية",
        ],
        "subtext": [
            "الكون أسبق من تفسير المشاهد",
            "الطاعة لا تحتاج ضجيجًا لتكون عظيمة",
            "الكبر يبدأ من وقفة تبدو صغيرة",
            "أثر الاختيار أطول من لحظته",
            "كل نار في القصة ستعود إلى الطين",
        ],
    },
    2: {
        "core_emotion": "فضول الأصل",
        "continuity_anchor": "المطر الذي يمحو آثار الحضارة",
        "tension_curve": [3, 4, 5, 6, 7],
        "beats": [
            "تفكيك العالم المألوف إلى أثر",
            "العودة عبر الزمن بدل شرحه",
            "كشف الأرض قبل الإنسان",
            "تقديم الطين بوصفه حامل المفارقة",
            "فتح سؤال التكريم والعداوة",
        ],
        "subtext": [
            "الحضارة نتيجة لا بداية",
            "كل أثر بشري يمكن أن يعود إلى التراب",
            "المكان ينتظر صاحبه قبل ظهوره",
            "الضعف المادي لا يحدد القيمة",
            "السؤال أقوى من الإعلان التفسيري",
        ],
    },
    3: {
        "core_emotion": "جلال النظام",
        "continuity_anchor": "الماء والخط المكتوب",
        "tension_curve": [2, 4, 6, 7, 8],
        "beats": [
            "تثبيت السكون البدئي",
            "تحويل الكتابة إلى حركة قدر",
            "اتساع الخط إلى كون مادي",
            "تمييز النور والنار بلا تجسيد",
            "ترك الأرض تنتظر الإعلان",
        ],
        "subtext": [
            "القصة تدخل كونًا له نظام",
            "المكتوب لا يعني غياب الاختيار",
            "الاتساع الكوني يخدم رحلة الإنسان",
            "اختلاف الأصل لا يمنح رتبة أخلاقية",
            "الاحتمال التفسيري يبقى في طرف الصورة",
        ],
    },
    4: {
        "core_emotion": "رهبة الوعد",
        "continuity_anchor": "الأرض والغبار المستقبلي",
        "tension_curve": [3, 5, 7, 9, 8],
        "beats": [
            "جعل الأرض موضوع انتظار",
            "إظهار إمكان العمران والفساد",
            "رفع سؤال الملائكة بلا تجسيد",
            "قطع الاحتمالات أمام العلم الإلهي",
            "إسقاط غبار المستقبل إلى مادة الخلق",
        ],
        "subtext": [
            "الخلافة تكليف قبل أن تكون مكانة",
            "الإنسان يحمل نقيضين ممكنين",
            "السؤال الصادق لا يساوي التمرد",
            "حدود العلم جزء من الحكمة",
            "المستقبل كله يبدأ من قبضة تراب",
        ],
    },
    5: {
        "core_emotion": "رهبة المادة",
        "continuity_anchor": "الماء داخل الطين والرنين الجوفاء",
        "tension_curve": [2, 4, 6, 8, 9],
        "beats": [
            "جمع ألوان الأرض في مادة واحدة",
            "إظهار تحولات الطين بلا جدول تعليمي",
            "الإيحاء بالتسوية من الداخل",
            "كشف الجوف والضعف",
            "استشعار اقتراب الخصم قبل الحياة",
        ],
        "subtext": [
            "التعدد الأرضي يدخل أصل الإنسان",
            "الوصف أغنى من ترتيب متكلف",
            "الهيئة لا تُعرض كي يبقى المعنى",
            "الهشاشة جزء من تركيب الإنسان",
            "العداوة تراقب الضعف قبل أن ترى العلم",
        ],
    },
    6: {
        "core_emotion": "دهشة الوعي",
        "continuity_anchor": "أول نبضة وأثر النفس",
        "tension_curve": [2, 5, 6, 7, 6],
        "beats": [
            "تحويل السكون إلى إدراك",
            "إدخال العالم عبر السمع والحركة",
            "جعل الحمد أول استجابة واعية",
            "إظهار المقياس عبر البيئة",
            "فتح الصلة بالسلام",
        ],
        "subtext": [
            "الحياة أثر لا مادة مصورة",
            "العالم يولد في الوعي لحظة بلحظة",
            "أول الكلام اعتراف بالمنعم",
            "العظمة الجسدية لا تساوي الكرامة وحدها",
            "الإنسان يبدأ علاقته بالآخر بالسلام",
        ],
    },
    7: {
        "core_emotion": "نشوة المعرفة",
        "continuity_anchor": "العناصر التي تجد أسماءها",
        "tension_curve": [3, 5, 7, 8, 9],
        "beats": [
            "تفكيك العالم إلى أشياء محسوسة",
            "ربط الأشياء بشبكة معنى",
            "عرض حدود العلم السابق",
            "منح التواضع لحظة صمت",
            "كشف موضع تكريم آدم",
        ],
        "subtext": [
            "المعرفة تبدأ من رؤية الفروق",
            "الاسم علاقة لا بطاقة جامدة",
            "الاعتراف بالحد ليس نقصًا أخلاقيًا",
            "الصمت هنا معرفة بمصدر المعرفة",
            "الطين يحمل ما لم تكشفه مادته",
        ],
    },
    8: {
        "core_emotion": "رهبة الامتحان",
        "continuity_anchor": "تجمد شبكة الأسماء",
        "tension_curve": [4, 6, 8, 9, 10],
        "beats": [
            "إيقاف نشوة المعرفة",
            "إحضار الأمر إلى مركز الصورة",
            "تهيئة حركة السجود",
            "زرع قياس النار والطين",
            "قطع المشهد قبل اكتمال الطاعة",
        ],
        "subtext": [
            "العلم لا يعفي من الامتثال",
            "الأمر يختبر ترتيب القيم",
            "الطاعة تتجمع قبل الحركة",
            "المادة ستُستعمل حجة للكبر",
            "التوتر يولد من التأخير لا الصخب",
        ],
    },
    9: {
        "core_emotion": "جلال الطاعة ثم الصدمة",
        "continuity_anchor": "الموجة الهابطة والتشوه الحراري",
        "tension_curve": [5, 7, 8, 9, 10],
        "beats": [
            "إطلاق السجود في مقياس ملحمي",
            "جعل البيئة تشارك في الامتثال",
            "إغلاق الحركة على اكتمالها",
            "فتح شق الاستثناء",
            "تحويل الشق إلى وادٍ للكبر",
        ],
        "subtext": [
            "الامتثال جماعي لكنه ليس ذوبانًا للمعنى",
            "الطبيعة تؤكد وحدة الاتجاه",
            "الكمال يسبق الانكسار كي نشعر بفداحته",
            "كلمة واحدة تعيد تفسير المشهد كله",
            "الرفض يصنع عالمه البصري الخاص",
        ],
    },
    10: {
        "core_emotion": "اشمئزاز الكبر وخطره",
        "continuity_anchor": "السبج والطريق المضيء",
        "tension_curve": [7, 8, 10, 9, 8],
        "beats": [
            "رفع النار ضد اتجاه الطاعة",
            "وضع النار والطين تحت السؤال",
            "تكبير الأنا داخل مرايا السبج",
            "إسقاط الكبر إلى العداوة",
            "مد العداوة على طريق البشر",
        ],
        "subtext": [
            "التمرد حركة عكسية مقصودة",
            "المادة لا تحاكم الأمر",
            "الكبر يعيد إنتاج نفسه في كل انعكاس",
            "العقوبة لا تنهي الاختيار الشرير",
            "كل إنسان سيرث طريقًا مراقبًا لا مصيرًا مفروضًا",
        ],
    },
    11: {
        "core_emotion": "ثقل العهد واتساع الذرية",
        "continuity_anchor": "الأثر الطيني الذي يصير أجيالًا",
        "tension_curve": [4, 6, 8, 7, 8],
        "beats": [
            "إخراج الكثرة من أصل واحد",
            "إقامة الميثاق في مركز الذاكرة الإنسانية",
            "مد الذرية إلى أمم وأزمنة",
            "فصل ثبوت الحدث عن ترتيب الربط الزمني",
            "إعادة المسؤولية إلى كل فرد",
        ],
        "subtext": [
            "البشرية امتداد حي لأبيها الأول",
            "العهد أسبق من دعوى الغفلة",
            "كل جيل يحمل السؤال نفسه",
            "التحفظ الزمني لا يضعف أصل الحدث",
            "العدو حاضر لكن الاختيار إنساني",
        ],
    },
    12: {
        "core_emotion": "الأنس تحت ظل التحذير",
        "continuity_anchor": "مساران في الحديقة",
        "tension_curve": [3, 4, 5, 6, 8],
        "beats": [
            "إثبات الخلق من الضلع بلا تشريح",
            "إبقاء التفاصيل غير الثابتة خارج يقين الصورة",
            "فتح الجنة بوصفها عالمًا حيًا",
            "إظهار الأنس عبر استجابة المكان",
            "إدخال العدو إلى حافة السكن",
        ],
        "subtext": [
            "الأنس يخرج من الوحدة دون ابتذال بصري",
            "الخبر الثانوي لا يقود التكوين",
            "النعيم يُعاش في البيئة لا في الزينة وحدها",
            "حضور اثنين يغير إيقاع العالم",
            "الخطر معروف قبل أن يصبح خفيًا",
        ],
    },
    13: {
        "core_emotion": "توتر المسافة",
        "continuity_anchor": "خط الظل والورقة غير المميزة",
        "tension_curve": [3, 5, 6, 8, 10],
        "beats": [
            "إظهار اتساع المباح",
            "تضييق المسار بلا حاجز مادي",
            "ترك احتمالات نوع الشجرة تتلاشى",
            "تثبيت الكاميرا عند الحد",
            "تسليم السكون إلى أثر الوسوسة",
        ],
        "subtext": [
            "الاختبار لا يولد من الحرمان",
            "الحد أخلاقي قبل أن يكون مكانيًا",
            "نوع الثمرة ليس مركز المعنى",
            "الطاعة تظهر في المسافة التي لا تُقطع",
            "الخطر يعرف أين يضغط قبل أن يتكلم",
        ],
    },
    14: {
        "core_emotion": "قلق الهمس ووعد العودة",
        "continuity_anchor": "الورقة والباب الذهبي",
        "tension_curve": [5, 6, 8, 7, 6],
        "beats": [
            "استعادة سكون الورقة",
            "إدخال اضطراب لا يملك شكلًا",
            "تضييق الممر نحو الهمس",
            "شق معنى السقوط بالتوبة",
            "إغلاق الحلقة على باب لا على هاوية",
        ],
        "subtext": [
            "المعصية لم تقع بعد",
            "الشر يبدأ بإعادة ترتيب المعنى",
            "الاقتراب أخطر حين يبدو نصيحة",
            "التوبة جزء من أفق الإنسان قبل عرضها",
            "المسلسل يعد بالعودة لا باليأس",
        ],
    },
}

NARRATION_REPLACEMENTS = {
    3: """كان الله، ولم يكن شيء غيره. وكان عرشه على الماء.

ثم خُلق القلم أولًا، وجاءه الأمر أن يكتب؛ فجرى بما هو كائن إلى قيام الساعة. وقبل أن تُخلق السماوات والأرض بخمسين ألف سنة، كانت مقادير الخلائق قد كُتبت.

بعدها اتسع المشهد: سماوات وأرض، ملائكة خُلقت من نور، وجان خُلق من مارج من نار.

ومن الجن كان إبليس.

وقبل أن يظهر آدم، تضعه بعض أخبار التفسير عند أطراف الحكاية. يبقى هناك، في ظل الرواية، فلا يتحول الاحتمال إلى يقين، ولا يتقدم إلى موضع لم يثبته النص.

لم يكن الإنسان بعد قد ظهر. لكن الكون الذي سيحمل قصته كان قد أُقيم على أمر وكتاب وحدود.""",
    11: f"""ولم تكن ذرية آدم غائبة عن أصل الامتحان.

أخرج الله من ظهر آدم ذريته، فامتد من الواحد نسل لا يُحصى؛ أجيال لم تولد بعد، وأمم ستعبر الأرض عصرًا بعد عصر.

وفي أصل قصة بني آدم قام الميثاق: {EXACT_COVENANT_VERSE}، فلا يقف الإنسان يوم القيامة خلف دعوى الغفلة.

هنا يثبت أصلان عظيمان: ذرية خرجت من أبيها الأول، وميثاق أقامه الله على بني آدم. أما موضع الربط الدقيق بين المشهدين داخل ترتيب الزمن، فيبقى حيث أبقاه الدليل؛ بلا ترتيب نجزم به.

العدو ينتظر على الطريق، لكن الإنسان لا يدخل الطريق بلا عهد ولا مسؤولية.

ومن هنا لم تعد قصة آدم قصة رجل واحد؛ صارت قصة كل قلب سيأتي من بعده.""",
    12: """ثم خلق الله لآدم زوجه.

وعرفتها السنة باسمها: حواء. ومن ضلع آدم خُلقت؛ فصار في العالم البشري أُنس بعد وحدة، وصارت الحكاية تمضي بحضور اثنين.

أما ما نسجته بعض الأخبار حول الجهة، والنوم، والكلمات، وسبب الاسم، فيبقى خلف ستار الحكاية؛ لا يدخل يقين الصورة، ولا يقود بناء المشهد.

قيل لهما: ﴿اسكن أنت وزوجك الجنة وكلا منها رغدًا حيث شئتما﴾.

لا جوع، ولا عري، ولا ظمأ، ولا شمس تؤذي.

ومع ذلك دخل التحذير إلى قلب السكن: ﴿إن هذا عدو لك ولزوجك فلا يخرجنكما من الجنة فتشقى﴾.

كان النعيم واسعًا، والعدو معروفًا، وبقي أن يظهر الحد.""",
    13: """وسط كل ذلك الاتساع، جاء النهي في موضع واحد: ﴿ولا تقربا هذه الشجرة فتكونا من الظالمين﴾.

تعددت الأسماء التي دارت حول الشجرة: حنطة، وكرم، وتين، وغيرها. لكن الوحي أبقى نوعها خارج الضوء؛ لأن مركز الامتحان لم يكن الثمرة، بل الأمر.

لم يكن الامتحان في الجوع؛ فالرغد يملأ المكان.

ولم يكن في كثرة المحرمات؛ فالممنوع حد واحد.

هنا تظهر الطاعة في أنقى صورها: أن تستطيع الاقتراب، وأن تملك الرغبة، ثم تعرف أن هناك مسافة لا ينبغي أن تُقطع.

والعدو الذي أعلن الحرب يعرف هذه المسافة جيدًا.""",
}

SEQUENCE_OVERRIDES = {
    11: {
        "sequence_title": "الميثاق والذرية",
        "dramatic_objective": (
            "توسيع قصة آدم إلى ذرية خرجت من ظهره وميثاق أقيم على بني آدم، "
            "مع حصر التحفظ في الربط الزمني الدقيق فقط."
        ),
        "pressure": (
            "إظهار أصل خروج الذرية والميثاق بصيغة جازمة من دون دمجهما في "
            "ترتيب زمني لا يثبته الدليل."
        ),
        "turn": "تنتقل الحرب من لحظة آدم إلى مسؤولية كل إنسان سيأتي بعده.",
        "visual_thesis": (
            "يخرج الامتداد البشري من أصل طيني واحد ثم ينتظم حول الميثاق، "
            "بلا جسد نبي ظاهر وبلا خط زمني زائف."
        ),
        "image_system": "الأصل الطيني، الذرية، الماء، شجرة النسب، العهد، الطريق",
        "sound_design": (
            "نبضة واحدة تتكاثر إلى آلاف النبضات، ثم تتحد عند الميثاق وتعود أفرادًا."
        ),
        "music_direction": (
            "ثيمة إنسانية تتسع من صوت منفرد إلى نسيج أجيال من دون كورال لغوي ممثل."
        ),
        "transition": "تتحول آخر نقطتين من الذرية إلى أثرين يدخلان خضرة الجنة.",
        "qualification_scope": {
            "EV-ADAM-061": (
                "CHRONOLOGICAL_LINK_ONLY; DESCENDANTS_EMERGENCE_AND_COVENANT_ORIGINS_ASSERTIVE"
            )
        },
    },
}

SHOT_OVERRIDES = {
    "ADAM-DC2-S11-SH01": {
        "composition": (
            "تكوين طيني قوسي هائل لا يكتمل في هيئة بشرية؛ من امتداده تبدأ "
            "آلاف نقاط الضوء في الظهور طبقة بعد طبقة."
        ),
        "camera": "انسحاب بطيء يبدأ من ملمس الطين وينتهي أمام اتساع لا يحصى.",
        "screen_action": (
            "تخرج النقاط من الأصل الطيني وتتحول إلى أجيال وقرى ومدن بعيدة."
        ),
        "sound_detail": "نبضة واحدة تتكاثر إلى نبضات بشرية متعددة الأعمار.",
        "transition_role": "إثبات خروج الذرية من أصل واحد قبل مشهد الميثاق.",
        "religious_visual_safety": (
            "لا جسد لآدم ولا ظهر مرئي؛ الأصل الطيني استعارة بيئية للحدث الثابت."
        ),
    },
    "ADAM-DC2-S11-SH02": {
        "composition": (
            "سطح ماء واسع يعكس أجيالًا بلا وجوه، وتتوسطه الآية بخط قرآني رصين."
        ),
        "camera": "هبوط محوري حتى يصير انعكاس السماء والأجيال مستوى واحدًا.",
        "screen_action": (
            f"تظهر {EXACT_COVENANT_VERSE} كاملة بلا تقطيع، وتتحد دوائر الماء عند «بَلَىٰ»."
        ),
        "sound_detail": "صوت الراوي وحده عند الآية، ثم عودة النبضات بعد الصمت.",
        "transition_role": "إقامة الميثاق بوصفه مركز المسؤولية لا هامشًا تفسيريًا.",
        "religious_visual_safety": "الآية تُقرأ بصوت الراوي؛ لا أداء جماعي مجسد للذرية.",
    },
    "ADAM-DC2-S11-SH03": {
        "composition": (
            "شجرة نسب من ضوء خافت تنمو فوق أرض حقيقية؛ فروعها تصير طرقًا ومدنًا وسواحل."
        ),
        "screen_action": "كل فرع يلد جيلًا ثم يترك أثرًا للجيل الذي بعده.",
        "transition_role": "تحويل الذرية من عدد غيبي إلى أثر بشري ممتد في الأرض.",
    },
    "ADAM-DC2-S11-SH04": {
        "composition": (
            "طريق واحد يمر عبر عصور متعددة من دون ساعة أو سهم زمني أو موضع محدد للحدث."
        ),
        "screen_action": (
            "تتعاقب العصور على جانبي الطريق بينما يبقى العهد في مركز التكوين."
        ),
        "transition_role": (
            "حفظ التحفظ في الربط الزمني من دون إضعاف أصل خروج الذرية أو الميثاق."
        ),
    },
    "ADAM-DC2-S12-SH02": {
        "composition": (
            "ثلاثة ظلال بيئية غير مكتملة: ممر ينعطف يسارًا، ضوء يخفت كالنوم، "
            "وشق في حجر يلتئم؛ لا تتجمع في واقعة واحدة."
        ),
        "camera": "انتقال تركيز بين الإشارات الثلاث ثم خروج منها إلى ضوء الحديقة.",
        "screen_action": "كل إشارة تبدأ بالتشكل ثم تذوب قبل أن تصبح صورة تقريرية.",
        "sound_detail": "أصوات بعيدة غير لغوية تنسحب أمام صوت الماء.",
        "transition_role": "إبقاء التفاصيل الثانوية خارج يقين الصورة بلا بطاقات بحثية.",
        "religious_visual_safety": "لا نوم مجسد ولا ضلع محدد الجهة ولا حوار مخترع.",
    },
    "ADAM-DC2-S13-SH03": {
        "composition": (
            "سنابل وعناقيد وتين تظهر كأصداء شفافة داخل عمق الغابة، لا كخيارات مكتوبة."
        ),
        "camera": "تبديل تركيز سينمائي بين الأصداء ثم العودة إلى غصن غير مميز.",
        "screen_action": "كل احتمال يقترب من الوضوح ثم يذوب قبل أن يستقر في المركز.",
        "sound_detail": "ثلاث خامات صوتية قصيرة تنتهي جميعًا في الصمت نفسه.",
        "transition_role": "صرف الانتباه عن نوع الثمرة وإعادته إلى الحد والأمر.",
        "religious_visual_safety": "لا تعيين بصري لنوع الشجرة ولا ادعاء تاريخي.",
    },
}


class StoryboardMasterError(ValueError):
    pass


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def read_json(path: Path) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StoryboardMasterError(f"Invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise StoryboardMasterError(f"Expected object: {path}")
    return value


def write_json(path: Path, value: Mapping[str, object]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _word_count(text: str) -> int:
    return len([token for token in text.split() if token.strip()])


def validate_inputs(
    *,
    script_v2: Mapping[str, object],
    storyboard_v2: Mapping[str, object],
    trace_v2: Mapping[str, object],
    approval_request_v2: Mapping[str, object],
    production_brief_v2: Mapping[str, object],
    episode_definition: Mapping[str, object],
) -> None:
    if script_v2.get("script_id") != PREDECESSOR_SCRIPT_ID:
        raise StoryboardMasterError("Unexpected Director's Cut v2 script id.")
    if script_v2.get("script_fingerprint") != PREDECESSOR_SCRIPT_FINGERPRINT:
        raise StoryboardMasterError("Unexpected Director's Cut v2 script fingerprint.")
    if storyboard_v2.get("storyboard_id") != PREDECESSOR_STORYBOARD_ID:
        raise StoryboardMasterError("Unexpected Director's Cut v2 storyboard id.")
    if storyboard_v2.get("storyboard_fingerprint") != PREDECESSOR_STORYBOARD_FINGERPRINT:
        raise StoryboardMasterError("Unexpected Director's Cut v2 storyboard fingerprint.")
    if trace_v2.get("trace_id") != PREDECESSOR_TRACE_ID:
        raise StoryboardMasterError("Unexpected Director's Cut v2 trace id.")
    if script_v2.get("sequence_count") != EXPECTED_SEQUENCE_COUNT:
        raise StoryboardMasterError("Expected fourteen sequences.")
    if storyboard_v2.get("shot_count") != EXPECTED_SHOT_COUNT:
        raise StoryboardMasterError("Expected seventy shots.")
    if script_v2.get("target_duration_seconds") != EXPECTED_TOTAL_SECONDS:
        raise StoryboardMasterError("Expected 1320 seconds.")
    if trace_v2.get("event_count") != EXPECTED_EVENT_COUNT:
        raise StoryboardMasterError("Expected 37 traced events.")
    if trace_v2.get("evidence_item_count") != EXPECTED_EVIDENCE_COUNT:
        raise StoryboardMasterError("Expected 57 traced evidence items.")
    if len(trace_v2.get("qualified_event_ids", [])) != EXPECTED_QUALIFIED_COUNT:
        raise StoryboardMasterError("Expected seven qualified events.")
    for artifact in (
        script_v2,
        storyboard_v2,
        trace_v2,
        approval_request_v2,
        production_brief_v2,
    ):
        if artifact.get("live_provider_execution") != LIVE_EXECUTION:
            raise StoryboardMasterError("Live execution must remain blocked.")
        if artifact.get("paid_execution") != PAID_EXECUTION:
            raise StoryboardMasterError("Paid execution must remain blocked.")
    if script_v2.get("human_script_approval") is not False:
        raise StoryboardMasterError("Predecessor script was unexpectedly approved.")
    if storyboard_v2.get("human_storyboard_approval") is not False:
        raise StoryboardMasterError("Predecessor storyboard was unexpectedly approved.")
    if episode_definition.get("evidence_gate_status") != (
        "OPEN_APPROVED_EVIDENCE_PACKAGE_BOUND"
    ):
        raise StoryboardMasterError("Evidence gate is not open.")


def _shot_master_fields(
    *,
    sequence_number: int,
    shot_number: int,
    shot: Mapping[str, object],
) -> dict:
    master = SEQUENCE_MASTERING[sequence_number]
    beat = master["beats"][shot_number - 1]
    subtext = master["subtext"][shot_number - 1]
    stages = ("entry", "reveal", "pressure", "turn", "bridge")
    stage = stages[shot_number - 1]
    duration = int(shot["duration_seconds"])
    if duration >= 22:
        rhythm = "deliberate_hold_with_internal_change"
    elif duration >= 15:
        rhythm = "measured_development"
    else:
        rhythm = "precise_acceleration"
    return {
        "dramatic_stage": stage,
        "dramatic_beat": beat,
        "visual_subtext": subtext,
        "entry_state": f"{master['core_emotion']} قبل تحقق نبضة {shot_number}",
        "exit_state": f"{master['core_emotion']} بعد تحقق نبضة {shot_number}",
        "camera_psychology": (
            f"الحركة تخدم «{beat}»؛ أي حركة لا تغيّر الإدراك أو الضغط تُرفض."
        ),
        "editorial_rhythm": rhythm,
        "cut_motivation": (
            "يحدث القطع عند اكتمال التحول داخل الكادر أو انتقال ذيل الصوت، "
            "لا عند انتهاء مدة اعتباطية."
        ),
        "continuity_anchor": master["continuity_anchor"],
        "sound_perspective": (
            f"الصوت يبدأ من مادة اللقطة ({shot['sound_detail']}) ثم يفتح أو يضغط المقياس."
        ),
        "acceptance_criteria": [
            f"تصل نبضة «{beat}» بلا شرح لفظي زائد",
            "تتغير المعلومة أو العاطفة داخل اللقطة",
            "تبقى السلامة الدينية واضحة من دون إضعاف القوة البصرية",
            "تسلم اللقطة عنصرًا بصريًا أو صوتيًا محددًا لما بعدها",
        ],
        "rejection_triggers": [
            "حركة كاميرا زخرفية",
            "صورة جميلة بلا تحول درامي",
            "تجريد عام يمكن نقله إلى أي حلقة",
            "إضاءة خيالية بلا وظيفة",
            "قطع لا تحمله حركة أو صوت أو معنى",
        ],
        "master_lock_status": "READY_FOR_HUMAN_STORYBOARD_REVIEW",
    }


def build_master_candidate(
    *,
    script_v2: Mapping[str, object],
    storyboard_v2: Mapping[str, object],
    trace_v2: Mapping[str, object],
    approval_request_v2: Mapping[str, object],
    production_brief_v2: Mapping[str, object],
) -> tuple[dict, dict, dict, dict, dict, dict]:
    script = copy.deepcopy(dict(script_v2))
    script["schema_version"] = SCRIPT_SCHEMA
    script["status"] = "HUMAN_REVIEW_REQUIRED_FINAL_MASTER_CANDIDATE"
    script["director_cut_version"] = VERSION
    script["final_dialogue_polish"] = "COMPLETE"
    script["source_context_literalism"] = "REMOVED"
    script["supersedes"] = {
        "script_id": PREDECESSOR_SCRIPT_ID,
        "script_fingerprint": PREDECESSOR_SCRIPT_FINGERPRINT,
    }

    for sequence in script["sequences"]:
        number = int(sequence["sequence_number"])
        if number in NARRATION_REPLACEMENTS:
            sequence["narration"] = NARRATION_REPLACEMENTS[number]
        if number in SEQUENCE_OVERRIDES:
            sequence.update(copy.deepcopy(SEQUENCE_OVERRIDES[number]))
        sequence["narration_word_count"] = _word_count(sequence["narration"])
        master = SEQUENCE_MASTERING[number]
        sequence["directorial_mastering"] = {
            "core_emotion": master["core_emotion"],
            "continuity_anchor": master["continuity_anchor"],
            "tension_curve": copy.deepcopy(master["tension_curve"]),
            "shot_escalation": copy.deepcopy(master["beats"]),
            "subtext_progression": copy.deepcopy(master["subtext"]),
            "editorial_rule": (
                "كل لقطة تدخل بحالة وتخرج بحالة مختلفة؛ لا مساحة لحركة زينة."
            ),
        }
        for shot in sequence["shots"]:
            override = SHOT_OVERRIDES.get(shot["shot_id"])
            if override:
                shot.update(copy.deepcopy(override))
            shot.update(
                _shot_master_fields(
                    sequence_number=number,
                    shot_number=int(shot["shot_number"]),
                    shot=shot,
                )
            )

    script["narration_word_count"] = sum(
        item["narration_word_count"] for item in script["sequences"]
    )
    script.pop("script_id", None)
    script.pop("script_fingerprint", None)
    script["script_fingerprint"] = canonical_sha256(script)
    script["script_id"] = (
        "adam_prestige_cinematic_script_v2_1_"
        + script["script_fingerprint"][:16]
    )

    storyboard = copy.deepcopy(dict(storyboard_v2))
    storyboard["schema_version"] = STORYBOARD_SCHEMA
    storyboard["status"] = "HUMAN_REVIEW_REQUIRED_FINAL_MASTER_CANDIDATE"
    storyboard["director_cut_version"] = VERSION
    storyboard["script_id"] = script["script_id"]
    storyboard["script_fingerprint"] = script["script_fingerprint"]
    storyboard["supersedes"] = {
        "storyboard_id": PREDECESSOR_STORYBOARD_ID,
        "storyboard_fingerprint": PREDECESSOR_STORYBOARD_FINGERPRINT,
    }
    storyboard["master_visual_grammar"] = copy.deepcopy(MASTER_VISUAL_GRAMMAR)
    storyboard["storyboard_completion"] = {
        "status": "COMPLETE_AWAITING_HUMAN_APPROVAL",
        "shots_with_dramatic_beat": EXPECTED_SHOT_COUNT,
        "shots_with_visual_subtext": EXPECTED_SHOT_COUNT,
        "shots_with_camera_psychology": EXPECTED_SHOT_COUNT,
        "shots_with_sound_perspective": EXPECTED_SHOT_COUNT,
        "shots_with_acceptance_criteria": EXPECTED_SHOT_COUNT,
        "shots_with_rejection_triggers": EXPECTED_SHOT_COUNT,
        "generic_placeholder_shots": 0,
        "unresolved_directorial_decisions": 0,
        "provider_execution_required_for_completion": False,
    }
    by_id = {
        shot["shot_id"]: shot
        for sequence in script["sequences"]
        for shot in sequence["shots"]
    }
    storyboard["shots"] = [
        copy.deepcopy(by_id[shot["shot_id"]])
        for shot in storyboard["shots"]
    ]
    storyboard.pop("storyboard_id", None)
    storyboard.pop("storyboard_fingerprint", None)
    storyboard["storyboard_fingerprint"] = canonical_sha256(storyboard)
    storyboard["storyboard_id"] = (
        "adam_detailed_cinematic_storyboard_v2_1_"
        + storyboard["storyboard_fingerprint"][:16]
    )

    trace = copy.deepcopy(dict(trace_v2))
    trace["schema_version"] = TRACE_SCHEMA
    trace["director_cut_version"] = VERSION
    trace["script_id"] = script["script_id"]
    trace["storyboard_id"] = storyboard["storyboard_id"]
    trace["qualification_scope"] = {
        "EV-ADAM-061": (
            "Chronological linkage remains qualified; emergence of Adam's descendants "
            "and the covenantal origin are narrated assertively."
        )
    }
    trace.pop("trace_id", None)
    trace["trace_id"] = (
        "adam_script_storyboard_trace_v2_1_"
        + canonical_sha256(trace)[:16]
    )

    audit = build_directorial_audit(script=script, storyboard=storyboard)

    approval_request = copy.deepcopy(dict(approval_request_v2))
    approval_request["schema_version"] = APPROVAL_REQUEST_SCHEMA
    approval_request["status"] = "FINAL_STORYBOARD_MASTER_HUMAN_APPROVAL_REQUIRED"
    approval_request["director_cut_version"] = VERSION
    approval_request["script_id"] = script["script_id"]
    approval_request["script_fingerprint"] = script["script_fingerprint"]
    approval_request["storyboard_id"] = storyboard["storyboard_id"]
    approval_request["storyboard_fingerprint"] = storyboard["storyboard_fingerprint"]
    approval_request["trace_id"] = trace["trace_id"]
    approval_request["directorial_audit_id"] = audit["audit_id"]
    approval_request["exact_approval_phrase"] = APPROVAL_PHRASE
    approval_request["exact_approval_phrase_sha256"] = hashlib.sha256(
        APPROVAL_PHRASE.encode("utf-8")
    ).hexdigest()
    approval_request["approval_effect"] = [
        "اعتماد النص السينمائي النهائي بإصدار 2.1",
        "اعتماد صحة صياغة الميثاق وخروج ذرية آدم مع حصر التأهيل في الربط الزمني",
        "اعتماد السلامة الدينية للنص",
        "اعتماد الستوريبورد الرئيسي ذي اللقطات السبعين",
        "السماح ببناء الهوية البصرية الرئيسية والأنيماتيك غير المدفوع",
        "عدم السماح بأي تشغيل مدفوع أو مباشر",
    ]
    approval_request["human_approval"] = False
    approval_request.pop("request_id", None)
    approval_request["request_id"] = (
        "adam_final_storyboard_master_approval_request_v2_1_"
        + canonical_sha256(approval_request)[:16]
    )

    production_brief = copy.deepcopy(dict(production_brief_v2))
    production_brief["schema_version"] = PRODUCTION_BRIEF_SCHEMA
    production_brief["director_cut_version"] = VERSION
    production_brief["script_id"] = script["script_id"]
    production_brief["storyboard_id"] = storyboard["storyboard_id"]
    production_brief["storyboard_master_status"] = (
        "COMPLETE_AWAITING_HUMAN_APPROVAL"
    )
    production_brief["next_non_paid_stage"] = (
        "MASTER_VISUAL_BIBLE_COLOR_SCRIPT_AND_ANIMATIC"
    )
    production_brief["generated_video_planned_seconds"] = 0
    production_brief["provider_selection"] = "DEFERRED"
    production_brief["budget_allocation"] = "DEFERRED"
    production_brief.pop("brief_id", None)
    production_brief["brief_id"] = (
        "adam_prestige_production_brief_v2_1_"
        + canonical_sha256(production_brief)[:16]
    )

    validate_outputs(
        script=script,
        storyboard=storyboard,
        trace=trace,
        approval_request=approval_request,
        production_brief=production_brief,
        audit=audit,
    )
    return script, storyboard, trace, approval_request, production_brief, audit


def build_directorial_audit(
    *,
    script: Mapping[str, object],
    storyboard: Mapping[str, object],
) -> dict:
    shots = storyboard["shots"]
    all_text = " ".join(
        str(value)
        for sequence in script["sequences"]
        for value in sequence.values()
        if isinstance(value, str)
    )
    audit = {
        "schema_version": DIRECTORIAL_AUDIT_SCHEMA,
        "status": "PASS_FINAL_STORYBOARD_MASTER_CANDIDATE",
        "episode_id": "episode-001-adam",
        "director_cut_version": VERSION,
        "shot_count": len(shots),
        "sequence_count": len(script["sequences"]),
        "duration_seconds": sum(int(shot["duration_seconds"]) for shot in shots),
        "dramatic_beat_coverage": sum(bool(shot.get("dramatic_beat")) for shot in shots),
        "visual_subtext_coverage": sum(bool(shot.get("visual_subtext")) for shot in shots),
        "camera_psychology_coverage": sum(bool(shot.get("camera_psychology")) for shot in shots),
        "sound_perspective_coverage": sum(bool(shot.get("sound_perspective")) for shot in shots),
        "acceptance_criteria_coverage": sum(bool(shot.get("acceptance_criteria")) for shot in shots),
        "rejection_trigger_coverage": sum(bool(shot.get("rejection_triggers")) for shot in shots),
        "unique_dramatic_beats": len({shot["dramatic_beat"] for shot in shots}),
        "generic_placeholder_shots": sum(
            any(token in str(shot).lower() for token in ("todo", "tbd", "placeholder"))
            for shot in shots
        ),
        "exact_covenant_verse_present": EXACT_COVENANT_VERSE in all_text,
        "malformed_covenant_text_present": any(
            phrase in all_text for phrase in ("قالوا بلى شهد:", "بربكمنا")
        ),
        "descendants_emergence_assertive": (
            "أخرج الله من ظهر آدم ذريته" in all_text
        ),
        "chronology_qualification_only": True,
        "research_meta_language_removed": not any(
            phrase in all_text for phrase in FORBIDDEN_NARRATION_PHRASES
        ),
        "v2_predecessor_preserved": True,
        "live_provider_execution": LIVE_EXECUTION,
        "paid_execution": PAID_EXECUTION,
    }
    audit["audit_id"] = (
        "adam_storyboard_master_directorial_audit_v2_1_"
        + canonical_sha256(audit)[:16]
    )
    return audit


def validate_outputs(
    *,
    script: Mapping[str, object],
    storyboard: Mapping[str, object],
    trace: Mapping[str, object],
    approval_request: Mapping[str, object],
    production_brief: Mapping[str, object],
    audit: Mapping[str, object],
) -> None:
    sequences = script.get("sequences")
    shots = storyboard.get("shots")
    if not isinstance(sequences, list) or len(sequences) != EXPECTED_SEQUENCE_COUNT:
        raise StoryboardMasterError("Script must have fourteen sequences.")
    if not isinstance(shots, list) or len(shots) != EXPECTED_SHOT_COUNT:
        raise StoryboardMasterError("Storyboard must have seventy shots.")
    if sum(int(item["duration_seconds"]) for item in sequences) != EXPECTED_TOTAL_SECONDS:
        raise StoryboardMasterError("Sequence duration must be 1320 seconds.")
    if sum(int(item["duration_seconds"]) for item in shots) != EXPECTED_TOTAL_SECONDS:
        raise StoryboardMasterError("Shot duration must be 1320 seconds.")
    if len({shot["shot_id"] for shot in shots}) != EXPECTED_SHOT_COUNT:
        raise StoryboardMasterError("Shot ids must remain unique.")
    if not 1200 <= int(script["narration_word_count"]) <= 1600:
        raise StoryboardMasterError("Narration density is outside the final range.")
    all_narration = "\n".join(sequence["narration"] for sequence in sequences)
    if EXACT_COVENANT_VERSE not in all_narration:
        raise StoryboardMasterError("Exact covenant verse is missing.")
    if "أخرج الله من ظهر آدم ذريته" not in all_narration:
        raise StoryboardMasterError("Descendants emergence is not assertive.")
    for phrase in FORBIDDEN_NARRATION_PHRASES:
        if phrase in all_narration:
            raise StoryboardMasterError(f"Forbidden narration phrase remains: {phrase}")
    sequence_11 = next(item for item in sequences if item["sequence_number"] == 11)
    if sequence_11.get("qualification_scope", {}).get("EV-ADAM-061") != (
        "CHRONOLOGICAL_LINK_ONLY; DESCENDANTS_EMERGENCE_AND_COVENANT_ORIGINS_ASSERTIVE"
    ):
        raise StoryboardMasterError("EV-ADAM-061 qualification scope is incorrect.")
    required_shot_fields = (
        "dramatic_beat",
        "visual_subtext",
        "entry_state",
        "exit_state",
        "camera_psychology",
        "editorial_rhythm",
        "cut_motivation",
        "continuity_anchor",
        "sound_perspective",
        "acceptance_criteria",
        "rejection_triggers",
        "master_lock_status",
    )
    for shot in shots:
        for field in required_shot_fields:
            if not shot.get(field):
                raise StoryboardMasterError(
                    f"Shot {shot['shot_id']} lacks master field {field}."
                )
        if shot.get("provider_execution") != LIVE_EXECUTION:
            raise StoryboardMasterError("Provider execution must remain blocked.")
    if len({shot["dramatic_beat"] for shot in shots}) != EXPECTED_SHOT_COUNT:
        raise StoryboardMasterError("Every shot must have a unique dramatic beat.")
    if audit.get("status") != "PASS_FINAL_STORYBOARD_MASTER_CANDIDATE":
        raise StoryboardMasterError("Directorial audit did not pass.")
    if audit.get("generic_placeholder_shots") != 0:
        raise StoryboardMasterError("Generic storyboard placeholders remain.")
    for key in (
        "dramatic_beat_coverage",
        "visual_subtext_coverage",
        "camera_psychology_coverage",
        "sound_perspective_coverage",
        "acceptance_criteria_coverage",
        "rejection_trigger_coverage",
    ):
        if audit.get(key) != EXPECTED_SHOT_COUNT:
            raise StoryboardMasterError(f"Incomplete directorial audit coverage: {key}")
    if trace.get("event_count") != EXPECTED_EVENT_COUNT:
        raise StoryboardMasterError("Trace event count changed.")
    if trace.get("evidence_item_count") != EXPECTED_EVIDENCE_COUNT:
        raise StoryboardMasterError("Trace evidence count changed.")
    if approval_request.get("human_approval") is not False:
        raise StoryboardMasterError("Human approval cannot be automatic.")
    for artifact in (
        script,
        storyboard,
        trace,
        approval_request,
        production_brief,
        audit,
    ):
        if artifact.get("live_provider_execution") != LIVE_EXECUTION:
            raise StoryboardMasterError("Live execution must remain blocked.")
        if artifact.get("paid_execution") != PAID_EXECUTION:
            raise StoryboardMasterError("Paid execution must remain blocked.")


def update_episode_definition(
    *,
    episode_definition: Mapping[str, object],
    script: Mapping[str, object],
    storyboard: Mapping[str, object],
    trace: Mapping[str, object],
    approval_request: Mapping[str, object],
    production_brief: Mapping[str, object],
    audit: Mapping[str, object],
) -> dict:
    definition = copy.deepcopy(dict(episode_definition))
    existing_revision = definition.get("director_cut_revision")
    existing_superseded_v2 = definition.get("superseded_directors_cut_v2")
    already_master = (
        isinstance(existing_revision, Mapping)
        and str(existing_revision.get("version")) == VERSION
    )
    if already_master:
        if not isinstance(existing_superseded_v2, Mapping):
            raise StoryboardMasterError("Master definition lacks superseded v2 record.")
        superseded_v2 = copy.deepcopy(dict(existing_superseded_v2))
    else:
        superseded_v2 = {
            "status": "SUPERSEDED_BY_FINAL_STORYBOARD_MASTER_V2_1",
            "script_id": PREDECESSOR_SCRIPT_ID,
            "script_fingerprint": PREDECESSOR_SCRIPT_FINGERPRINT,
            "storyboard_id": PREDECESSOR_STORYBOARD_ID,
            "storyboard_fingerprint": PREDECESSOR_STORYBOARD_FINGERPRINT,
            "trace_id": PREDECESSOR_TRACE_ID,
            "cinematic_script": copy.deepcopy(definition.get("cinematic_script")),
            "detailed_storyboard": copy.deepcopy(definition.get("detailed_storyboard")),
        }
    if (
        superseded_v2.get("script_fingerprint") != PREDECESSOR_SCRIPT_FINGERPRINT
        or superseded_v2.get("storyboard_fingerprint")
        != PREDECESSOR_STORYBOARD_FINGERPRINT
    ):
        raise StoryboardMasterError("Superseded v2 fingerprints changed.")
    definition["superseded_directors_cut_v2"] = superseded_v2
    definition["cinematic_script"] = {
        "status": "HUMAN_REVIEW_REQUIRED_FINAL_MASTER_CANDIDATE",
        "path": "editorial/prestige-cinematic-script-v2-1.json",
        "markdown_path": "editorial/prestige-cinematic-script-v2-1.md",
        "script_id": script["script_id"],
        "input_fingerprint": script["script_fingerprint"],
        "human_approval": False,
        "director_cut_version": VERSION,
    }
    definition["detailed_storyboard"] = {
        "status": "HUMAN_REVIEW_REQUIRED_FINAL_MASTER_CANDIDATE",
        "path": "cinematic/detailed-storyboard-v2-1.json",
        "csv_path": "cinematic/detailed-storyboard-v2-1.csv",
        "storyboard_id": storyboard["storyboard_id"],
        "input_fingerprint": storyboard["storyboard_fingerprint"],
        "human_approval": False,
        "director_cut_version": VERSION,
    }
    definition["script_storyboard_trace"] = {
        "status": "PASS_COMPLETE_TRACE",
        "path": "evidence/script-storyboard-evidence-trace-v2-1.json",
        "trace_id": trace["trace_id"],
    }
    definition["script_storyboard_approval_request"] = {
        "status": "HUMAN_APPROVAL_REQUIRED",
        "path": "evidence/script-storyboard-human-approval-request-v2-1.json",
        "request_id": approval_request["request_id"],
    }
    definition["production_brief"] = {
        "status": "PLANNING_ONLY_PROVIDER_EXECUTION_BLOCKED",
        "path": "cinematic/prestige-production-brief-v2-1.json",
        "brief_id": production_brief["brief_id"],
    }
    definition["storyboard_directorial_audit"] = {
        "status": audit["status"],
        "path": "cinematic/storyboard-master-directorial-audit-v2-1.json",
        "audit_id": audit["audit_id"],
    }
    definition["director_cut_revision"] = {
        "version": VERSION,
        "status": "FINAL_MASTER_CANDIDATE_AWAITING_HUMAN_APPROVAL",
        "adaptation_policy": "MEANING_PRESERVED_WORDING_CINEMATICALLY_ADAPTED",
        "source_context_literalism": "REMOVED",
        "research_meta_language": "REMOVED",
        "descendants_emergence": "ASSERTIVE",
        "covenant_verse_text": EXACT_COVENANT_VERSE,
        "chronological_linkage": "QUALIFIED_ONLY",
        "script_fingerprint": script["script_fingerprint"],
        "storyboard_fingerprint": storyboard["storyboard_fingerprint"],
        "supersedes_script_fingerprint": PREDECESSOR_SCRIPT_FINGERPRINT,
        "supersedes_storyboard_fingerprint": PREDECESSOR_STORYBOARD_FINGERPRINT,
    }
    definition["storyboard_completion_status"] = (
        "COMPLETE_AWAITING_HUMAN_APPROVAL"
    )
    definition["next_stage"] = "HUMAN_REVIEW_OF_FINAL_STORYBOARD_MASTER_V2_1"
    definition["live_execution_status"] = LIVE_EXECUTION
    definition["paid_execution"] = PAID_EXECUTION
    definition["timezone_policy"]["canonical_local_timezone"] = TIMEZONE
    return definition


def render_script_markdown(script: Mapping[str, object]) -> str:
    lines = [
        "# سراج: التاريخ الإسلامي",
        "",
        "## الحلقة الأولى: آدم — التكريم والاختبار — Final Storyboard Master v2.1",
        "",
        f"**المدة المستهدفة:** {script['target_duration_seconds'] // 60} دقيقة",
        f"**عدد التسلسلات:** {script['sequence_count']}",
        f"**عدد كلمات التعليق:** {script['narration_word_count']}",
        "",
        "> المعنى ودرجة الجزم محفوظان، والصياغة والصورة والإيقاع محررة "
        "سينمائيًا لخدمة الدراما.",
        "",
    ]
    for sequence in script["sequences"]:
        master = sequence["directorial_mastering"]
        lines.extend(
            [
                f"## {sequence['sequence_number']:02d}. {sequence['sequence_title']}",
                "",
                f"**المدة:** {sequence['duration_seconds']} ثانية",
                f"**الوظيفة الدرامية:** {sequence['narrative_function']}",
                f"**الهدف:** {sequence['dramatic_objective']}",
                f"**الضغط:** {sequence['pressure']}",
                f"**التحول:** {sequence['turn']}",
                f"**العاطفة المركزية:** {master['core_emotion']}",
                f"**مرساة الاستمرارية:** {master['continuity_anchor']}",
                "",
                "### التعليق الصوتي",
                "",
                sequence["narration"],
                "",
                "### المعالجة الإخراجية",
                "",
                f"- الأطروحة البصرية: {sequence['visual_thesis']}",
                f"- نظام الصورة: {sequence['image_system']}",
                f"- تصميم الصوت: {sequence['sound_design']}",
                f"- الموسيقى: {sequence['music_direction']}",
                f"- الانتقال: {sequence['transition']}",
                f"- منحنى التوتر: {master['tension_curve']}",
                f"- الأحداث: {', '.join(sequence['event_ids']) or 'تحريري'}",
                f"- القيود: {', '.join(sequence['qualification_labels']) or 'لا يوجد'}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_outputs(
    *,
    output_root: Path,
    script: Mapping[str, object],
    storyboard: Mapping[str, object],
    trace: Mapping[str, object],
    approval_request: Mapping[str, object],
    production_brief: Mapping[str, object],
    audit: Mapping[str, object],
    episode_definition: Mapping[str, object],
) -> dict[str, Path]:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    outputs = {
        "script_json": output_root / "prestige-cinematic-script-v2-1.json",
        "script_markdown": output_root / "prestige-cinematic-script-v2-1.md",
        "storyboard_json": output_root / "detailed-storyboard-v2-1.json",
        "storyboard_csv": output_root / "detailed-storyboard-v2-1.csv",
        "trace": output_root / "script-storyboard-evidence-trace-v2-1.json",
        "approval_request": output_root / "script-storyboard-human-approval-request-v2-1.json",
        "production_brief": output_root / "prestige-production-brief-v2-1.json",
        "audit": output_root / "storyboard-master-directorial-audit-v2-1.json",
        "episode_definition": output_root / "episode-definition-v1.json",
        "readme": output_root / "README.md",
    }
    write_json(outputs["script_json"], script)
    outputs["script_markdown"].write_text(
        render_script_markdown(script), encoding="utf-8", newline="\n"
    )
    write_json(outputs["storyboard_json"], storyboard)
    write_json(outputs["trace"], trace)
    write_json(outputs["approval_request"], approval_request)
    write_json(outputs["production_brief"], production_brief)
    write_json(outputs["audit"], audit)
    write_json(outputs["episode_definition"], episode_definition)
    with outputs["storyboard_csv"].open("w", encoding="utf-8-sig", newline="") as stream:
        fields = [
            "shot_id", "sequence_id", "duration_seconds", "treatment",
            "dramatic_stage", "dramatic_beat", "visual_subtext", "composition",
            "camera", "camera_psychology", "screen_action", "lighting_and_colour",
            "sound_detail", "sound_perspective", "cut_motivation",
            "continuity_anchor", "transition_role", "religious_visual_safety",
            "master_lock_status", "event_ids", "evidence_ids",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for shot in storyboard["shots"]:
            row = {key: shot[key] for key in fields}
            row["event_ids"] = "|".join(shot["event_ids"])
            row["evidence_ids"] = "|".join(shot["evidence_ids"])
            writer.writerow(row)
    outputs["readme"].write_text(
        "# Adam Final Storyboard Master v2.1\n\n"
        "This package finalizes the 22-minute, 14-sequence, 70-shot storyboard "
        "candidate. Every shot carries a dramatic beat, visual subtext, camera "
        "psychology, sound perspective, continuity anchor, acceptance criteria, "
        "and rejection triggers. The covenant verse is corrected exactly; the "
        "emergence of Adam's descendants is assertive, while only the precise "
        "chronological linkage remains qualified. No paid, direct, live, or "
        "Runware execution is authorised.\n",
        encoding="utf-8", newline="\n"
    )
    archive = output_root.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(output_root.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(output_root).as_posix())
    outputs["archive"] = archive
    return outputs
