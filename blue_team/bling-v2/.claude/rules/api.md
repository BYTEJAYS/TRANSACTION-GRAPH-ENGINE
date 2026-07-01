---
paths:
  - "src/api/**"
  - "api/**"
  - "routes/**"
  - "src/routes/**"
  - "**/*.api.ts"
  - "**/*endpoint*"
---

# API Design Rules

## REST Conventions
- Resource names are nouns, lowercase, plural: `/users`, `/orders`, `/products`
- Nested resources max 2 levels deep: `/users/{id}/orders` — not `/users/{id}/orders/{id}/items/{id}`
- Actions that don't map to CRUD use a verb sub-resource: `POST /orders/{id}/cancel`
- Never use verbs in resource paths: `/getUser` is wrong, `/users/{id}` is correct

## Versioning
- All routes prefixed with version: `/v1/users`, `/v2/products`
- Never remove or rename a field in an existing version — add a new version
- Deprecation: announce in response headers (`Deprecation`, `Sunset`) before removing

## Request Shape
- Accept `application/json` for all write operations (POST, PUT, PATCH)
- Validate request body with schema before any business logic runs
- Reject unknown fields with 400 rather than silently ignoring them

## Response Shape
- Consistent wrapper on all responses:
  ```json
  { "data": {...}, "error": null, "meta": {...} }
  ```
  (or check agent_docs/api.md for this project's established wrapper)
- `data` is null on error; `error` is null on success — never both present, never both null
- `meta` carries pagination info, request IDs, deprecation notices

## Status Codes
- 200 OK — GET success, PUT/PATCH success
- 201 Created — POST that creates a new resource (include `Location` header)
- 204 No Content — DELETE success, or action with no response body
- 400 Bad Request — unparseable request or schema violation
- 401 Unauthorized — no valid authentication provided
- 403 Forbidden — authenticated but lacks permission
- 404 Not Found — resource doesn't exist (or hidden for security)
- 409 Conflict — state conflict (duplicate key, optimistic lock failure)
- 422 Unprocessable Entity — schema valid but business validation failed
- 429 Too Many Requests — rate limit exceeded (include `Retry-After` header)
- 500 Internal Server Error — unexpected failure; never expose internals

## Error Format
```json
{ "error": { "code": "INVALID_EMAIL", "message": "Email address is not valid", "field": "email" } }
```
- `code`: machine-readable string constant — clients can `switch` on this
- `message`: human-readable, safe to display in UI
- `field`: present when error is tied to a specific request field

## Pagination
- Page-based for small, bounded datasets: `?page=2&per_page=20`
- Cursor-based for large or frequently-updated datasets: `?after=cursor_token&limit=20`
- Always include in `meta`: `{ "total": 1042, "has_more": true, "next_cursor": "abc123" }`
- Default page size: 20. Max page size: 100. Enforce — never return unbounded results.

## Idempotency
- GET, PUT, DELETE must be idempotent — calling twice = same result as calling once
- POST that creates resources is not idempotent — use `Idempotency-Key` header for retryable POSTs
