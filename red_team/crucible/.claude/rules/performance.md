---
paths:
  - "src/services/**"
  - "src/api/**"
  - "src/db/**"
  - "services/**"
  - "api/**"
  - "routes/**"
  - "src/routes/**"
---

# Performance Rules

## Database
- N+1 detection: a query inside a loop is always an N+1. Use eager loading or batch fetching.
- Never load an entire table — always add LIMIT or paginate
- Use indexes for every column you filter or sort by in hot paths
- Avoid `SELECT *` — select only the columns your code actually uses
- Batch writes: insert/update multiple rows in one statement, not one per row

## Caching
- Identify cache candidates: reference data (countries, categories), expensive aggregations, external API responses
- Every cache entry has an explicit TTL — no indefinite caching
- Cache invalidation strategy documented before caching anything
- Cache at the right layer: DB query cache vs application cache vs HTTP cache vs CDN

## Async & Concurrency
- Never block the event loop in Node.js — all I/O must be async
- In Python async code: never call sync I/O inside an async function (use run_in_executor)
- Fan out independent async operations in parallel (`Promise.all` / `asyncio.gather`) — not sequential await
- Set timeouts on all external calls (HTTP, DB, queue) — never wait indefinitely

## Pagination
- Any query that could return >100 rows must paginate — no exceptions
- Default page size ≤ 20 for API responses; max size ≤ 100
- Cursor-based pagination for datasets that grow or update frequently

## Response Size
- Never return full nested objects when IDs suffice for the client's use case
- Trim unused fields from API responses — less data = faster transfer + parsing
- Compress responses: enable gzip/brotli on the server
- Images and static assets served via CDN, not application server

## Measurement First
- Do not optimize without a measurement. Profile before refactoring for performance.
- Define the threshold before optimizing: "under 200ms p95" is a target; "faster" is not.
- Add structured logging for slow operations: log query time, external call time, total request time.
