from pathlib import Path

files = [
    "src/application/workflow/documentary_workflow.py",
    "src/test_script_generator.py",
    "src/test_scene_generator_v2.py",
    "src/test_image_prompt_engineer.py",
    "src/test_documentary_pipeline.py",
    "src/test_llm_pipeline.py",
]

for file in files:
    p = Path(file)

    if not p.exists():
        continue

    text = p.read_text(encoding="utf-8")

    text = text.replace(
        "from application.llm.fake_llm_client import FakeLLMClient",
        "from application.llm.provider_factory import ProviderFactory"
    )

    text = text.replace(
        "FakeLLMClient()",
        "ProviderFactory.create()"
    )

    p.write_text(text, encoding="utf-8")

print("Migration completed.")
