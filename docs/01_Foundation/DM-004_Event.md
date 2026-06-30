# DM-004 — Event Entity

Version: 0.1

Status: Draft

---

# Purpose

Defines the Event entity used throughout the Siraj Platform.

---

# Required Properties

- Entity ID
- Name
- Arabic Name
- Event Type

---

# Optional Properties

- Start Date
- End Date
- Primary Place
- Summary

---

# Event Types

- Birth
- Death
- Battle
- Migration
- Treaty
- Revelation
- Journey
- Construction
- Appointment
- Speech

---

# Relationships

An Event may:

- involve Persons
- occur at Places
- reference Sources
- contain Claims
- precede or follow other Events
- belong to a Timeline

---

# Rules

- Every Event has one permanent Entity ID.
- Events never store historical evidence directly.
- Claims and Sources remain independent.
- An Event may have multiple interpretations.

---

End of Draft.