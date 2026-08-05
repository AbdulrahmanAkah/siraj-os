from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

RELEASE = "RUNWARE_IMAGE_MODEL_SELECTION_AND_LOCK_V1"
SEEDREAM_MODEL = "bytedance:seedream@5.0-pro"
NANO_BANANA_MODEL = "google:4@3"
FLUX_2_PRO_MODEL = "bfl:5@1"

PRIMARY_ROLES = frozenset({"DEFAULT","ENVIRONMENT_WIDE","INTERIOR_ATMOSPHERE","SYMBOLIC_SAFE","DYNAMIC_ACTION","MATERIAL_OBJECTS"})
SECONDARY_ROLES = frozenset({"HUMAN_CLOSEUP","HUMAN_CROWD_COMPLEX","CHARACTER_CONSISTENCY","REFERENCE_EDIT","HUMAN_INTERACTION_COMPLEX"})
ALL_ROLES = PRIMARY_ROLES | SECONDARY_ROLES

NANO_TERMS = ("portrait","close-up","close up","closeup","crowd","busy market","many people","character consistency","same character","reference image","human interaction","facial detail","بورتريه","لقطة قريبة","حشد","سوق مزدحم","عدة أشخاص","ثبات الشخصية","نفس الشخصية","صورة مرجعية","تفاعل بشري")
SEEDREAM_TERMS = ("wide establishing","environment","landscape","interior","atmosphere","symbolic","sandstorm","storm","dynamic action","architecture","material","بيئة","منظر واسع","داخلي","أجواء","رمزي","عاصفة","حركة ديناميكية","عمارة","خامات")

class ImageModelRoutingError(RuntimeError):
    pass

@dataclass(frozen=True, slots=True)
class ImageRoute:
    role: str
    model: str
    provider: str
    width: int
    height: int
    reference_images_allowed: int
    reason: str
    include_cost: bool = True
    number_results: int = 1


def _text(shot: Mapping[str, Any]) -> str:
    fields=("label_ar","dramatic_function_ar","visual_brief_ar","camera_motion_ar","runware_positive_prompt_en","runware_negative_prompt_en")
    return " ".join(str(shot.get(f,"")) for f in fields).lower()


def _references(shot: Mapping[str, Any]) -> tuple[str,...]:
    value=shot.get("reference_images")
    if isinstance(value, Sequence) and not isinstance(value,(str,bytes)):
        return tuple(str(x) for x in value if str(x).strip())
    inputs=shot.get("inputs")
    if isinstance(inputs, Mapping):
        value=inputs.get("referenceImages")
        if isinstance(value, Sequence) and not isinstance(value,(str,bytes)):
            return tuple(str(x) for x in value if str(x).strip())
    return ()


def classify_image_role(shot: Mapping[str, Any]) -> tuple[str,str]:
    explicit=shot.get("image_model_role") or shot.get("runware_image_role")
    if isinstance(explicit,str) and explicit.strip():
        role=explicit.strip().upper()
        if role not in ALL_ROLES:
            raise ImageModelRoutingError(f"UNKNOWN_IMAGE_MODEL_ROLE:{role}")
        return role,"EXPLICIT_STORYBOARD_ROLE"
    if _references(shot):
        return "REFERENCE_EDIT","REFERENCE_IMAGES_PRESENT"
    if str(shot.get("character_continuity_id") or shot.get("character_identity_id") or "").strip():
        return "CHARACTER_CONSISTENCY","CHARACTER_CONTINUITY_ID_PRESENT"
    text=_text(shot)
    if any(term in text for term in NANO_TERMS):
        if "crowd" in text or "حشد" in text or "سوق مزدحم" in text:
            return "HUMAN_CROWD_COMPLEX","COMPLEX_HUMAN_CROWD_SIGNAL"
        if any(term in text for term in ("portrait","close-up","close up","closeup","بورتريه","لقطة قريبة")):
            return "HUMAN_CLOSEUP","HUMAN_CLOSEUP_SIGNAL"
        return "HUMAN_INTERACTION_COMPLEX","COMPLEX_HUMAN_SIGNAL"
    if any(term in text for term in SEEDREAM_TERMS):
        if "symbolic" in text or "رمزي" in text:
            return "SYMBOLIC_SAFE","SYMBOLIC_SCENE_SIGNAL"
        if "interior" in text or "داخلي" in text:
            return "INTERIOR_ATMOSPHERE","INTERIOR_SCENE_SIGNAL"
        if any(term in text for term in ("sandstorm","storm","dynamic action","عاصفة","حركة ديناميكية")):
            return "DYNAMIC_ACTION","DYNAMIC_ACTION_SIGNAL"
        if any(term in text for term in ("wide establishing","environment","landscape","بيئة","منظر واسع")):
            return "ENVIRONMENT_WIDE","ENVIRONMENT_SIGNAL"
        return "MATERIAL_OBJECTS","MATERIAL_OR_ARCHITECTURE_SIGNAL"
    return "DEFAULT","PRIMARY_DEFAULT"


def route_image_shot(shot: Mapping[str, Any]) -> ImageRoute:
    treatment=str(shot.get("final_budget_treatment","")).upper()
    if treatment=="GRAPHICS":
        raise ImageModelRoutingError("GRAPHICS_SHOT_MUST_USE_GRAPHICS_PIPELINE")
    if treatment=="GENERATED_VIDEO":
        raise ImageModelRoutingError("VIDEO_SHOT_MUST_USE_VIDEO_MODEL_ROUTING")
    if treatment and treatment!="ANIMATED_STILL_COMPOSITING":
        raise ImageModelRoutingError(f"UNSUPPORTED_IMAGE_TREATMENT:{treatment}")
    role,reason=classify_image_role(shot)
    refs=_references(shot)
    if role in SECONDARY_ROLES:
        if len(refs)>14:
            raise ImageModelRoutingError("NANO_BANANA_REFERENCE_IMAGE_LIMIT_EXCEEDED")
        return ImageRoute(role,NANO_BANANA_MODEL,"GOOGLE_VIA_RUNWARE",1344,768,14,reason)
    if len(refs)>10:
        raise ImageModelRoutingError("SEEDREAM_REFERENCE_IMAGE_LIMIT_EXCEEDED")
    return ImageRoute(role,SEEDREAM_MODEL,"BYTEDANCE_VIA_RUNWARE",1424,800,10,reason)


def build_runware_image_task(shot: Mapping[str, Any], task_uuid: str) -> dict[str, Any]:
    if not task_uuid.strip():
        raise ImageModelRoutingError("TASK_UUID_REQUIRED")
    prompt=str(shot.get("runware_positive_prompt_en","")).strip()
    if not prompt:
        raise ImageModelRoutingError("POSITIVE_PROMPT_REQUIRED")
    route=route_image_shot(shot)
    task={"taskType":"imageInference","taskUUID":task_uuid.strip(),"model":route.model,"positivePrompt":prompt,"width":route.width,"height":route.height,"numberResults":1,"outputFormat":"JPG","outputType":"URL","includeCost":True}
    negative=str(shot.get("runware_negative_prompt_en","")).strip()
    if negative:
        task["negativePrompt"]=negative
    refs=_references(shot)
    if refs:
        task["inputs"]={"referenceImages":list(refs)}
    task["sirajRouting"]={"release":RELEASE,"role":route.role,"reason":route.reason,"primary_model":SEEDREAM_MODEL,"secondary_model":NANO_BANANA_MODEL,"excluded_model":FLUX_2_PRO_MODEL}
    return task
