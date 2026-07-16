# MODULE_BOUNDARIES.md

# Knowledge Engine

Responsible for:

* Extraction
* Parsing
* Validation
* Repository
* Knowledge Graph

Must never know:

* Scripts
* Scenes
* Images

---

# Documentary Engine

Responsible for:

* Narrative
* Outline
* Script

Must never know:

* Storage
* LLM Providers
* Artifacts

---

# Production Engine

Responsible for:

* Scene Planning
* Scene Generation
* Image Prompt Generation

Must never manipulate KnowledgeGraph directly.

---

# Artifact Engine

Responsible for:

* Artifact creation
* Artifact persistence
* Output packaging

---

# Infrastructure

Responsible only for:

* External APIs
* Persistence
* Storage
* LLM Providers

Never owns business rules.

---

# Core

Contains only runtime primitives shared across modules.

Core must remain infrastructure-independent.
