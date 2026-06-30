# DM-003 — Place Entity

Version: 0.1

Status: Draft

---

# Purpose

Defines the Place entity used throughout the Siraj Platform.

---

# Required Properties

- Entity ID
- Name
- Arabic Name
- Type

---

# Optional Properties

- Alternative Names
- Parent Place
- Coordinates
- Description
- Historical Notes

---

# Place Types

- City
- Village
- Region
- Country
- Desert
- Mountain
- River
- Valley
- Building
- Mosque

---

# Relationships

A Place may:

- contain other Places
- host Events
- be associated with Persons
- belong to Organizations
- have Claims
- reference Sources

---

# Rules

- Every Place has one permanent Entity ID.
- Places may change names over time.
- Historical claims are stored separately.
- Places may exist within other Places.

---

End of Draft.