# Siraj Architect

## Vision

Siraj is not a content generator.

Siraj is a knowledge compiler.

Its purpose is to transform verified knowledge into multiple forms of educational content.

Knowledge is permanent.

Content is only one possible representation of knowledge.

## Core Principles

- Clean Architecture
- Explicit models
- Deterministic services
- Single Responsibility Principle
- Fail Fast
- Small focused classes
- No hidden behaviour
- Architecture before implementation

## Layers

### Domain

Contains business knowledge.

Examples:

- Entity
- Source
- Claim
- KnowledgeAsset

Domain must not depend on any other layer.

### Application

Contains orchestration logic.

Examples:

- SirajEngine
- ScriptStructureBuilder
- Future AI orchestration

Application depends on Domain.

### Infrastructure

Contains external implementations.

Examples:

- Storage
- Database
- APIs
- LLM Providers

Infrastructure depends on Application and Domain.

## Pipeline

KnowledgeAsset

↓

Outline

↓

ScriptStructure

↓

ContentSpecification

↓

Prompt

↓

LLM

↓

ScriptDraft

↓

Media Export

## Rules

Never return anonymous dictionaries inside the application pipeline.

Every pipeline stage must communicate using explicit models.

Domain models represent knowledge.

Application models represent processing artifacts.

Infrastructure models represent external systems.

## Engineering Rules

Never use Any.

Never introduce hidden behaviour.

Never modify files outside the assigned task.

Never implement features that were not requested.

Prefer composition over inheritance.

Keep classes small.

Keep methods focused.

One responsibility per class.

## Testing Rules

Every capability must include tests.

Tests must contain assertions.

Printing objects is not sufficient as verification.

Every completed capability must include execution evidence.

## Code Review Checklist

Before considering a task complete, verify:

- Architecture preserved
- No unnecessary abstractions
- No duplicated logic
- No feature creep
- Explicit models used
- Tests updated
- Execution evidence available

## Decision Authority

Architecture decisions belong to the project architect.

Implementation decisions belong to the implementation agent.

The implementation agent must not redesign the architecture.

End of document.
