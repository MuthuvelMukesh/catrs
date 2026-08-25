---
applyTo: services/audit-service/**
---

# Audit service guardrails

- Never import from services/routing-engine or from its Python package modules.
- Use only versioned contract files or independent read-only data access for policy validation.
- Keep the audit path technologically independent from the routing engine even during prototypes.
