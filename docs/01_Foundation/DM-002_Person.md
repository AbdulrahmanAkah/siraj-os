# DM-002 — Person Entity

Version: 0.1

Status: Draft

---

# Purpose

Defines the Person entity used throughout the Siraj Platform.

---

# Required Properties

- Entity ID
- Full Name
- Arabic Name
- Type
- Gender
- Birth Date
- Death Date

---

# Optional Properties

- Kunya
- Titles
- Lineage
- Tribe
- Father
- Mother
- Spouses
- Children
- Occupation
- Biography

---

# Relationships

A Person may:

- participate in Events
- live in Places
- belong to Organizations
- own Objects
- reference Sources
- have Claims
- know other Persons

---

# Rules

- Every Person has one permanent Entity ID.
- A Person never stores historical claims directly.
- Claims are stored separately and linked to the Person.
- Every relationship is traceable.

---

End of Draft.