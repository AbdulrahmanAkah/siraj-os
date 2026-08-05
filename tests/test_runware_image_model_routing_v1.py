from src.application.runware_image_model_routing_v1 import *


def shot(**kw):
    d={"final_budget_treatment":"ANIMATED_STILL_COMPOSITING","runware_positive_prompt_en":"Cinematic ancient environment","visual_brief_ar":"بيئة تاريخية واسعة"}
    d.update(kw); return d

def test_primary_environment():
    r=route_image_shot(shot()); assert r.model==SEEDREAM_MODEL and r.role=="ENVIRONMENT_WIDE"

def test_secondary_closeup():
    r=route_image_shot(shot(visual_brief_ar="لقطة قريبة لشخصية")); assert r.model==NANO_BANANA_MODEL and r.role=="HUMAN_CLOSEUP"

def test_reference_routes_secondary():
    r=route_image_shot(shot(reference_images=["https://example.com/x.jpg"])); assert r.model==NANO_BANANA_MODEL and r.role=="REFERENCE_EDIT"

def test_dynamic_action_stays_primary():
    r=route_image_shot(shot(runware_positive_prompt_en="Dynamic action in a sandstorm")); assert r.model==SEEDREAM_MODEL and r.role=="DYNAMIC_ACTION"

def test_payload_cost_and_flux_excluded():
    p=build_runware_image_task(shot(),"task"); assert p["includeCost"] is True and p["model"]!=FLUX_2_PRO_MODEL
