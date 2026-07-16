# DEPENDENCY_RULES.md

# Allowed Dependencies

CLI

↓

Pipeline

↓

Workflow

↓

Application

↓

Domain

↓

Infrastructure

---

# Forbidden Dependencies

Domain → Application

Domain → Infrastructure

Infrastructure → Application Models

Workflow → Infrastructure

Builders → Repositories

Repositories → LLM Providers

---

# Repository Rules

Repositories may:

* Save
* Load
* Query

Repositories may NOT:

* Generate
* Parse
* Build Graphs
* Call LLMs

---

# Workflow Rules

Workflow coordinates.

Workflow never owns business logic.

Workflow never transforms knowledge.

Workflow never performs persistence.

---

# Builder Rules

Builders construct objects.

Builders never access storage.

Builders never invoke LLM providers directly.

---

# Generator Rules

Generators consume models.

Generators produce models.

Generators never own orchestration.

---

# Graph Rules

KnowledgeGraph is immutable after construction.

Graph mutation occurs only through GraphBuilder.

---

# Import Rules

Lower layers never import upper layers.

Application may depend on Domain.

Domain depends only on itself.
