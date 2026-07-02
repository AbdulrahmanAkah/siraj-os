# SIRAJ Reasoning Principles

Version: 1.0

Status: Active

---

# Purpose

This document defines the permanent reasoning philosophy of SIRAJ.

These principles are intended to remain stable throughout the lifetime of the project.

Every architectural decision, reasoning engine, planner, or AI integration should follow these principles.

Whenever implementation details conflict with these principles, the principles take precedence.

---

# Principle 1

## Knowledge is the Source of Truth

Knowledge exists independently from language.

Language describes knowledge.

Language does not create knowledge.

All generated content must originate from structured knowledge already present inside the system.

---

# Principle 2

## Large Language Models Are Writers

Language models are responsible for:

* Writing
* Rewriting
* Summarization
* Style adaptation
* Natural language generation

Language models are NOT responsible for:

* Creating facts
* Inventing relationships
* Selecting evidence
* Organizing knowledge
* Determining historical truth

SIRAJ performs reasoning.

The language model performs expression.

---

# Principle 3

## Representation Before Reasoning

Knowledge must first be represented explicitly.

Only after knowledge is represented can reasoning begin.

Representation includes:

* Entities
* Claims
* Sources
* Relationships
* Context
* Organized Knowledge

Reasoning engines consume structured knowledge.

They never consume raw text whenever a structured representation exists.

---

# Principle 4

## Reasoning Must Be Explainable

Every reasoning engine should produce deterministic outputs whenever possible.

A decision made by SIRAJ should always be explainable.

Whenever two users receive different outputs, there must be an explicit reason.

Randomness should never become part of knowledge reasoning.

---

# Principle 5

## Separation of Responsibilities

Each layer has exactly one responsibility.

Knowledge Layer

Stores knowledge.

Organization Layer

Organizes knowledge.

Reasoning Layer

Makes decisions.

Planning Layer

Creates narrative plans.

Prompt Layer

Communicates with language models.

Generation Layer

Produces human language.

Presentation Layer

Formats output for the target platform.

Responsibilities must never overlap.

---

# Principle 6

## Knowledge Must Be Traceable

Every generated paragraph should be traceable back to:

* Claims
* Sources
* Relationships

Nothing should appear in generated content without a traceable origin.

Future versions should support complete provenance tracking.

---

# Principle 7

## Deterministic Before Intelligent

Whenever deterministic rules can solve a problem, they should be preferred over AI.

AI should only be introduced when deterministic reasoning is insufficient.

This makes the system:

* More reliable
* Easier to debug
* Easier to verify
* Easier to maintain

---

# Principle 8

## AI Assists Reasoning

AI enhances reasoning.

AI never replaces reasoning.

Reasoning engines remain the primary decision makers.

Language models assist only where explicit reasoning becomes impractical.

---

# Principle 9

## Architecture Evolves, Principles Do Not

Implementation details may change.

Classes may change.

Services may change.

Pipelines may change.

The reasoning philosophy should remain stable.

---

# Principle 10

## Knowledge is an Asset

Every KnowledgeAsset should become more valuable over time.

New information should enrich existing knowledge rather than replace it.

Knowledge accumulation is preferred over regeneration.

---

# Principle 11

## Relationships Are First-Class Citizens

Facts rarely exist in isolation.

Relationships between entities, events, claims, and sources are part of knowledge itself.

Reasoning engines should prefer explicit relationships over inferring them repeatedly.

---

# Principle 12

## Planning Precedes Writing

A good document is planned before it is written.

Narrative planning must happen before prompt construction.

Prompt construction must happen before language generation.

Writing should never determine structure.

Structure determines writing.

---

# Principle 13

## Platform Independence

Knowledge should remain independent of its final presentation.

The same knowledge should be reusable for:

* Documentary
* Podcast
* Article
* Course
* Book
* Short Video

Only planning and presentation should change.

Knowledge remains constant.

---

# Principle 14

## Incremental Intelligence

SIRAJ should become smarter through specialized reasoning engines.

Examples include:

* Claim Selection
* Timeline Extraction
* Citation Mapping
* Relationship Discovery
* Event Ordering
* Contradiction Detection

Each engine should improve one capability without affecting unrelated parts of the system.

---

# Principle 15

## Long-Term Maintainability

Short-term convenience must never compromise long-term architecture.

Every new feature should improve the system while preserving clarity, modularity, and extensibility.

SIRAJ is designed to evolve over years, not weeks.
