# DM-001 — Siraj Domain Model

Version: 0.1

Status: Draft

---

# Purpose

This document defines the core domain objects of the Siraj Platform.

Every future component must build upon these definitions.

---

# Core Entity Types

## Person

Represents any historical human.

Examples:

- Prophet
- Companion
- Scholar
- King
- Caliph
- Soldier

---

## Place

Represents any geographical location.

Examples:

- City
- Village
- Region
- Mountain
- River
- Desert

---

## Event

Represents something that happened at a specific time.

Examples:

- Battle
- Birth
- Death
- Migration
- Treaty
- Revelation

---

## Source

Represents an information source.

Examples:

- Quran
- Hadith Collection
- Historical Book
- Academic Paper
- Manuscript

---

## Claim

Represents a statement about an entity.

Examples:

"Person X was born in Year Y."

"Battle Z happened after Event A."

Claims are never treated as absolute truth.
They must reference one or more Sources.

---

## Organization

Represents a structured group.

Examples:

- Tribe
- State
- Army
- Dynasty

---

## Object

Represents physical items.

Examples:

- Weapon
- Building
- Clothing
- Currency
- Tool

---

## Time

Represents historical time.

Examples:

- Year
- Month
- Era
- Hijri Date
- BCE / CE

---

# Core Principles

1. Everything is an Entity.

2. Every Entity has a unique ID.

3. Every Claim references Sources.

4. Sources have reliability.

5. Relationships are first-class objects.

6. Knowledge is separated from presentation.

7. AI consumes knowledge but never owns it.

---

End of Draft.