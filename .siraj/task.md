You ignored the requested architecture.

Create these files:

src/application/documentary/knowledge_outline_builder.py
src/application/narrative/narrative_builder.py
src/application/script/script_generator.py

Update:

src/application/workflow/documentary_workflow.py

Workflow:

KnowledgeRepository
-> KnowledgeOutlineBuilder
-> NarrativeBuilder
-> ScriptGenerator
-> ScenePlanner
-> SceneGenerator
-> ImagePromptGenerator

Requirements:

- Do not use application/services/*
- Do not use legacy NarrativeBuilder
- No placeholders
- Actually create the missing files
- Return only when all files are created
