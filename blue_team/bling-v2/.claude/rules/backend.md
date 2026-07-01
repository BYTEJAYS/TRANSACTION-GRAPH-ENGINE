---
paths:
  - "src/api/**"
  - "src/routes/**"
  - "src/services/**"
  - "api/**"
  - "routes/**"
  - "services/**"
  - "app/**/*.py"
  - "**/*router*"
  - "**/*controller*"
  - "**/*handler*"
---

# Backend / API Rules

## Request Handling
- Validate ALL inputs at the boundary before any business logic runs
- Use schema validation (Pydantic / Zod / Joi) — not manual if/else checks
- Never trust client-provided IDs for ownership — verify server-side
- Reject unknown fields — do not silently ignore extra input

## Response Shape
- All responses follow the project's standard wrapper (check agent_docs/api.md)
- 4xx errors include a human-readable `message` field
- 5xx errors: log full detail server-side, return generic message to client
- Never expose stack traces, internal paths, or system details to the client
- HTTP status codes must be semantically correct:
  - 200 OK, 201 Created (POST that creates a resource), 204 No Content (DELETE success)
  - 400 Bad Request (malformed/unparseable), 401 Unauthorized (not authenticated),
    403 Forbidden (authenticated but no permission), 404 Not Found,
    422 Unprocessable Entity (schema-valid but fails business validation),
    429 Too Many Requests, 500 Internal Server Error
- PUT and DELETE endpoints must be idempotent (calling twice = same result as calling once)

## Security
- Auth middleware applied before handler logic — never inside the handler
- Parameterized queries only — no string concatenation with user data
- Rate limiting on all public endpoints
- No sensitive data (passwords, tokens, PII) in response bodies or logs

## Code Structure
- Route handlers: routing and response only — no business logic
- Business logic: services layer only
- DB access: repository/model layer only
- One responsibility per function — if the name needs "and", split it

## Error Handling
- Every external call (DB, API, filesystem) has explicit error handling
- Fail loudly with a useful message — never swallow exceptions silently
- Use typed error classes, not bare `raise Exception("message")`
