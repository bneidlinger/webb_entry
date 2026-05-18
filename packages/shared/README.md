# @webbwatch/shared

Language-neutral schemas and types that need to round-trip between the Python services and the TS frontend.

- `schemas/` — JSON Schema documents (source of truth).
- `types/` — Generated/hand-written TS types (downstream of `schemas/`).

The Python services should validate against the JSON Schemas using `pydantic` models that mirror them. The frontend should import from `types/`.
