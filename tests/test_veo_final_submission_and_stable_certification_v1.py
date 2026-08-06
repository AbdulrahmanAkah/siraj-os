import ast
from pathlib import Path

from src.application import desktop_media_execution_v1 as media


def _function_node(source: str, name: str) -> ast.FunctionDef:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"FUNCTION_NOT_FOUND:{name}")


def _call_lines(function: ast.FunctionDef, name: str) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        called = node.func
        if isinstance(called, ast.Name) and called.id == name:
            lines.append(node.lineno)
    return sorted(lines)


def test_veo_final_submission_removes_negative_prompt() -> None:
    task, certification = (
        media._siraj_prepare_veo_final_submission_v1(
            {
                "taskType": "videoInference",
                "taskUUID": "00000000-0000-0000-0000-000000000001",
                "model": "google:veo@3.1-lite",
                "width": 1280,
                "height": 720,
                "numberResults": 1,
                "outputType": "URL",
                "outputFormat": "MP4",
                "includeCost": True,
                "deliveryMethod": "async",
                "duration": 8,
                "positivePrompt": "Approved cinematic prompt.",
                "negativePrompt": "text, watermark, duplicate subjects",
                "providerSettings": {
                    "google": {
                        "generateAudio": False,
                        "personGeneration": "dont_allow",
                    }
                },
            },
            {"status": "PASS"},
            "VID-SH-001-C01",
        )
    )
    assert "negativePrompt" not in task
    assert (
        "Strict exclusion constraints for this provider request:"
        in task["positivePrompt"]
    )
    assert certification is not None
    assert certification[
        "unsupported_negativePrompt_parameter"
    ] == "REMOVED_BEFORE_NETWORK"


def test_mutable_asset_plan_is_not_raw_fingerprinted() -> None:
    gate = Path(
        "src/application/production_pipeline_certification_gate_v1.py"
    ).read_text(encoding="utf-8")
    assert "SIRAJ_MUTABLE_ASSET_PLAN_FINGERPRINT_EXCLUSION_V1" in gate
    assert "production-standard-v2-native-asset-plan-v1.json" in gate


def test_executor_sanitizes_after_luna_and_before_network() -> None:
    source = Path(
        "src/application/desktop_media_execution_v1.py"
    ).read_text(encoding="utf-8")
    function = _function_node(source, "execute_runware_item")

    luna_lines = _call_lines(
        function,
        "apply_certified_prompt_to_task",
    )
    sanitizer_lines = _call_lines(
        function,
        "_siraj_prepare_veo_final_submission_v1",
    )
    network_lines = _call_lines(
        function,
        "_post_json",
    )

    assert luna_lines
    assert sanitizer_lines == [sanitizer_lines[0]]
    assert network_lines
    assert min(luna_lines) < sanitizer_lines[0] < min(network_lines)
