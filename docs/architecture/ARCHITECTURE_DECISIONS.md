# ARCHITECTURE_DECISIONS.md

# SIRAJ OS Architecture Decision Records (ADR)

Version: 1.0

Status: Active

---

# ADR-001

## Decision

SirajOS is a **Knowledge Operating System**, not a script generator.

## Rationale

The primary asset of the project is knowledge.

Scripts, scenes and prompts are derived artifacts.

Therefore every production pipeline must originate from the Knowledge Engine.

---

# ADR-002

## Decision

Knowledge Graph is the semantic core of the system.

## Rationale

Every documentary, book, podcast or future product consumes the same knowledge graph.

Knowledge must never be regenerated independently for each product.

---

# ADR-003

## Decision

Workflow coordinates.

Workflow does not implement business logic.

## Rationale

Business logic belongs inside specialized services.

Keeping orchestration separated prevents the Workflow layer from becoming a God Object.

---

# ADR-004

## Decision

Every concept has exactly one Canonical Model.

## Rationale

Duplicate models inevitably diverge over time.

Single Source of Truth guarantees consistency.

---

# ADR-005

## Decision

Domain remains independent from all external technologies.

## Rationale

Business knowledge should survive replacement of:

* LLM providers
* databases
* storage engines
* frameworks

---

# ADR-006

## Decision

LLM Providers are Infrastructure.

## Rationale

OpenAI, Gemini or future providers are implementation details.

Changing provider must never require Domain modifications.

---

# ADR-007

## Decision

Application owns use cases.

Domain owns business rules.

Infrastructure owns implementation.

## Rationale

This preserves Clean Architecture boundaries.

---

# ADR-008

## Decision

Every production artifact must be reproducible.

## Rationale

Given identical knowledge and identical inputs, SirajOS should be capable of regenerating identical outputs.

This enables auditing and debugging.

---

# ADR-009

## Decision

Builders create.

Generators produce.

Repositories persist.

Services execute.

## Rationale

Responsibilities remain explicit and discoverable.

---

# ADR-010

## Decision

Knowledge precedes narrative.

## Pipeline

Knowledge

↓

Organization

↓

Narrative

↓

Outline

↓

Script

↓

Scenes

↓

Image Prompts

↓

Artifacts

## Rationale

Narrative must emerge from verified knowledge rather than arbitrary prompting.

---

# ADR-011

## Decision

Graph mutations occur only through GraphBuilder.

## Rationale

Prevent uncontrolled modifications to the semantic graph.

---

# ADR-012

## Decision

Every architectural refactor must preserve observable behavior.

## Rationale

Refactoring changes structure, not functionality.

Behavioral changes require independent feature proposals.

---

# ADR-013

## Decision

No architectural shortcut may introduce technical debt intentionally.

## Rationale

Temporary fixes become permanent architecture.

All compromises must be documented before implementation.

---

# ADR-014

## Decision

Architecture documentation is part of the source code.

## Rationale

Documents inside docs/architecture are authoritative project assets and must evolve alongside the codebase.

---

# ADR Update Policy

A new ADR must be created whenever one of the following changes:

* Core architecture
* Layer boundaries
* Canonical models
* Workflow topology
* Knowledge pipeline
* Persistence strategy
* Plugin architecture
* External integration strategy

Existing ADRs are never rewritten.

They are superseded by newer ADRs to preserve architectural history.
