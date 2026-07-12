from pathlib import Path

wrappers = {

"src/domain/claims/claim.py":
"""from domain.knowledge_objects.claim import Claim
__all__ = ["Claim"]
""",

"src/domain/sources/source.py":
"""from domain.knowledge_objects.source import Source
__all__ = ["Source"]
""",

"src/domain/relationships/relationship.py":
"""from domain.knowledge_objects.relationship import Relationship
__all__ = ["Relationship"]
""",

"src/application/models/llm/prompt.py":
"""from application.models.prompt import Prompt
__all__ = ["Prompt"]
""",

"src/application/llm/core/llm_gateway.py":
"""from application.ports.llm_gateway import LLMGateway
__all__ = ["LLMGateway"]
""",

"src/application/models/documentary/timeline_event.py":
"""from domain.knowledge_objects.timeline_event import TimelineEvent
__all__ = ["TimelineEvent"]
""",
}


for path, content in wrappers.items():

    p = Path(path)

    if p.exists():
        p.write_text(
            content,
            encoding="utf-8"
        )
        print("Updated:", path)


print("Batch compatibility migration complete")
