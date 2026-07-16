# SIRAJ OS — Refactor Master Plan (Version 1.0)

**Status:** Architectural Baseline Approved

**Based on:** Comprehensive architecture audit and dependency analysis.

---

# Executive Summary

The architecture of SIRAJ OS is fundamentally sound.

The project **does not require a rewrite**.

Instead, it requires a sequence of controlled architectural refactors that:

* remove duplication,
* stabilize the Domain,
* isolate orchestration,
* prepare the project for long-term growth.

The existing architecture is estimated to be approximately **85–90% of the desired final architecture**.

The remaining work is architectural cleanup.

---

# Guiding Principle

From this point onward, **no feature development should introduce new architectural debt**.

Every future feature must either:

* follow the final architecture,

or

* improve the current architecture.

Never the opposite.

---

# Refactor Roadmap

## Phase 0 — Architecture Freeze

Status:

Completed.

No structural redesigns should be made without updating this document.

---

# Phase 1 — Canonical Model Consolidation

Priority:

★★★★★

Goal:

Every concept must have exactly one authoritative definition.

Current duplicates include:

* Claim
* Relationship
* Source
* Prompt
* Script
* Outline
* TimelineEvent

Deliverables:

* Single Source of Truth for every model.
* Remove obsolete duplicates.
* Update imports.

Expected Risk:

Medium.

---

# Phase 2 — Workflow Decomposition

Priority:

★★★★★

Current problem:

DocumentaryWorkflow orchestrates almost every subsystem directly.

Target architecture:

Workflow becomes only a coordinator.

Introduce:

* KnowledgeWorkflow
* DocumentaryWorkflow
* ProductionWorkflow

Workflow should coordinate modules—not execute business logic.

Expected Risk:

Medium.

---

# Phase 3 — Application Layer Cleanup

Priority:

★★★★★

Current problem:

application contains mixed organizational styles.

Current mixture:

* Layers
* Features
* Helpers

Target:

Feature-oriented modules.

Example:

application/

knowledge/

documentary/

scene/

image/

llm/

planning/

Each feature owns its builders, services, DTOs, and orchestrators.

Expected Risk:

Low.

---

# Phase 4 — Services Cleanup

Priority:

★★★★☆

Current problem:

services contains builders, facades, helpers and actual services.

Target:

Separate:

Builders

Services

Facades

Utilities

Each folder should have one architectural responsibility.

Expected Risk:

Low.

---

# Phase 5 — Core Cleanup

Priority:

★★★★☆

Current problem:

Core currently mixes wrappers with domain abstractions.

Target:

core becomes infrastructure-independent runtime primitives only.

Anything that merely forwards imports should disappear.

Expected Risk:

Low.

---

# Phase 6 — Documentary Pipeline Cleanup

Priority:

★★★★☆

Current problems:

Generator

Builder

Outline

Planner

share unclear boundaries.

Goal:

Pipeline becomes:

Knowledge

↓

Narrative

↓

Outline

↓

Script

↓

Scenes

↓

Images

↓

Artifacts

Each stage owns only one responsibility.

Expected Risk:

Low.

---

# Phase 7 — Infrastructure Expansion

Priority:

★★★☆☆

Current infrastructure is minimal.

Future modules:

Storage

Persistence

Embeddings

Search

Vector Database

Cache

External APIs

Queues

Infrastructure must never leak into Domain.

---

# Phase 8 — Testing Architecture

Priority:

★★★☆☆

Introduce:

Unit Tests

Integration Tests

Workflow Tests

Golden Dataset Tests

Regression Tests

Current tests should be reorganized by feature.

---

# Phase 9 — Dependency Hardening

Priority:

★★★☆☆

Introduce automated validation that guarantees:

No forbidden imports.

No circular dependencies.

No duplicate canonical models.

Every commit should validate architecture automatically.

---

# Phase 10 — Plugin Architecture

Priority:

★★☆☆☆

Future objective:

Allow new content engines without modifying the core.

Examples:

Book Generator

Podcast Generator

Course Generator

Interactive Timeline Generator

All should plug into the same Knowledge Engine.

---

# Architectural Rules

These rules become permanent.

---

## Rule 1

One concept.

One class.

One authoritative implementation.

---

## Rule 2

Domain never imports Infrastructure.

---

## Rule 3

Workflow coordinates.

Services execute.

Builders construct.

Repositories persist.

---

## Rule 4

Application owns use cases.

Domain owns business rules.

Infrastructure owns external systems.

---

## Rule 5

Every new module must have one clear responsibility.

---

## Rule 6

Never duplicate models.

Extend them.

Do not recreate them.

---

## Rule 7

Knowledge Graph remains the canonical semantic layer.

Nothing bypasses it.

---

# Refactor Order (Mandatory)

1.

Canonical Models

↓

2.

Workflow

↓

3.

Application cleanup

↓

4.

Services cleanup

↓

5.

Core cleanup

↓

6.

Documentary pipeline

↓

7.

Infrastructure

↓

8.

Testing

↓

9.

Architecture validation

↓

10.

Plugins

Changing this order increases technical risk.

---

# Components That Must Not Be Modified Until Phase 1 Completes

KnowledgeGraph

KnowledgeNode

KnowledgeEdge

GraphIndex

Relationship Engine

Knowledge Parser

Changing these early risks cascading failures.

---

# Components Safe To Refactor Early

KnowledgeRepository

Workflow

ProductionPipeline

Application Models

Services

Core wrappers

---

# Current Architectural Health

Architecture Quality:

9.2 / 10

Scalability:

9.5 / 10

Maintainability:

8.5 / 10

Modularity:

8.8 / 10

Extensibility:

9.4 / 10

Technical Debt:

Moderate but localized.

---

# Final Assessment

SIRAJ OS already possesses the foundations of a professional knowledge operating system.

Its remaining challenges are architectural refinement rather than architectural rescue.

Once the roadmap above is completed, the project will possess a stable foundation suitable for long-term expansion into multiple AI-driven content production systems without requiring another large-scale structural redesign.
