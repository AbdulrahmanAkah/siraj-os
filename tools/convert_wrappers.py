from pathlib import Path

wrappers = {

"src/application/models/llm/prompt.py":
"from src.application.models.prompt import Prompt\n\n__all__=['Prompt']",

"src/application/llm/core/llm_gateway.py":
"from src.application.ports.llm_gateway import LLMGateway\n\n__all__=['LLMGateway']",

"src/application/documentary/documentary_outline.py":
"from src.application.models.outline import DocumentaryOutline\n\n__all__=['DocumentaryOutline']",

"src/application/services/narrative_builder.py":
"from src.application.narrative.narrative_builder import NarrativeBuilder\n\n__all__=['NarrativeBuilder']",

}

for path, content in wrappers.items():

    p=Path(path)

    if p.exists():

        p.write_text(
            content,
            encoding="utf-8"
        )

        print("Converted:", path)
