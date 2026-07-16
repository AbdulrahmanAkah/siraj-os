# SirajOS Canonical Model Registry

## Purpose

This document defines the official canonical location for each core concept.
Duplicate implementations must be migrated toward these definitions.

---

# Domain Models

| Concept | Canonical Location |
|---|---|
| Person | domain.knowledge_objects.person |
| Event | domain.knowledge_objects.event |
| Claim | domain.knowledge_objects.claim |
| Source | domain.knowledge_objects.source |
| Relationship | domain.relationships.relationship |

---

# Application Models

| Concept | Canonical Location |
|---|---|
| Script | application.models.documentary.script |
| Prompt | application.models.prompt |
| TimelineEvent | application.models.documentary.timeline_event |
| DocumentaryOutline | application.models.outline |
| ScenePlan | application.planning.scene_plan |

---

# Interfaces

| Concept | Canonical Location |
|---|---|
| LLMGateway | application.ports.llm_gateway |

---

# Migration Rules

1. New code MUST import from canonical locations only.
2. Old modules remain temporarily as compatibility layers.
3. Deletion happens only after dependency verification.
4. Domain objects must not be duplicated inside application.
5. Application services must depend on domain abstractions.

---

Status:
Architecture Refactor Phase 1
