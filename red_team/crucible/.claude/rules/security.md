# Security Rules
# No paths: frontmatter — loads every session, applies everywhere.
# These are the rules too important to be context-dependent.

## Secrets — Non-Negotiable
- Secrets go in .env only. Never in source files, config files, or comments.
- .env must be in .gitignore. Verified at every session start.
- New env vars: add the name (not the value) to .env.example.
- If you write a value that looks like a secret into any source file — stop immediately.

## Input Validation — Applied at Every Entry Point
- Validate before any business logic runs
- Reject and return an error on invalid input — never silently discard or coerce
- User input never reaches: SQL queries, shell commands, template rendering, eval()
- File paths from user input: validate against an allowlist of allowed directories

## Authentication
- Use established libraries — never custom crypto or custom auth flows
- Passwords: bcrypt or argon2 with appropriate cost factor — never MD5/SHA1/SHA256
- Sessions: server-side expiry enforced, invalidatable on logout
- Tokens: short-lived access tokens + rotatable refresh tokens
- Auth checks: middleware applied at the router level, not inside individual handlers

## HTTP Security
- Set these headers on every HTTP response:
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains`
  - `Content-Security-Policy` — define explicitly, avoid `unsafe-inline` without nonce/hash
  - `X-Frame-Options: DENY` (or SAMEORIGIN if embedding your own content)
  - `X-Content-Type-Options: nosniff`
  - `Referrer-Policy: strict-origin-when-cross-origin`
- CORS: explicit origin allowlist only. Never `Access-Control-Allow-Origin: *` on routes that accept credentials or auth tokens.
- Rate limiting on all auth endpoints: login, register, forgot-password, token refresh.
- Rate limiting on all public write endpoints (POST, PUT, PATCH, DELETE).

## Output Safety
- Never send stack traces to client in any environment except local dev
- Never log: passwords, tokens, session IDs, credit card numbers, SSNs, PII
- API errors: log full detail server-side, return generic message to client
- File downloads: Content-Disposition header set to prevent execution

## Dependencies
- Before adding any new package: check npmjs.com/pypi.org for publisher legitimacy
- Run pip-audit or npm audit when adding dependencies
- Lock files committed and reviewed on updates
- No packages with critical/high CVEs without documented mitigation

## The One Rule That Covers Everything
If user-controlled data touches a sensitive operation (query, command, file, render),
there must be explicit validation between the input and the operation.
No exceptions. No "we'll add it later."
