# RM-001 — Relationship Model

Version: 0.1

Status: Draft

---

# Purpose

Defines how Entities are connected inside the Siraj Platform.

Relationships are first-class objects.

---

# Core Principle

Relationships are independent objects with their own identity.

They are not simple fields inside entities.

---

# Structure

Relationship

- Relationship ID
- Type
- Source Entity
- Target Entity
- Start Date
- End Date
- Evidence
- Confidence
- Notes

---

# Initial Relationship Types

## Family

- father_of
- mother_of
- child_of
- spouse_of
- sibling_of

---

## Location

- born_in
- died_in
- lived_in
- buried_in

---

## Participation

- participated_in
- led
- witnessed
- authored
- narrated

---

## Organization

- member_of
- ruled
- governed
- belonged_to

---

## Time

- before
- after
- during

---

# Rules

- Every relationship has its own ID.
- Every relationship references one or more Sources.
- Every relationship has a confidence level.
- Relationships may change over time.
- Relationships never exist without two valid entities.

---

End of Draft.