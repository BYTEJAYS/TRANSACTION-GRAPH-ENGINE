---
paths:
  - "tests/**"
  - "test/**"
  - "**/*.test.ts"
  - "**/*.test.tsx"
  - "**/*.test.js"
  - "**/*.spec.ts"
  - "**/*.spec.js"
  - "**/*_test.py"
  - "**/test_*.py"
  - "**/__tests__/**"
---

# Testing Rules

## What Must Be Tested
- Every public function: at least one happy path + one failure mode
- Every bug fix: regression test that would have caught that specific bug
- Every API endpoint: success response + auth failure + validation failure
- Every database operation: happy path + constraint violation
- Boundary conditions: empty, null/None, zero, negative, max length

## What Not to Test
- Implementation details — test behavior, not internals
- Third-party library code
- Code already covered by type checking
- Private/internal methods directly (test through the public interface)

## Test Quality Rules
- One assertion per test where possible
- Test names describe the scenario: `test_login_fails_with_expired_token` not `test_login_2`
- Tests are independent — no shared mutable state, no order dependency
- Deterministic — same result every run, no time-dependent or random behavior
- Fast — unit tests under 100ms, integration tests under 2s (mark slow tests)

## Mocks & Fixtures
- No mocks unless: real network call OR paid external API
- Prefer real behavior with test database over mocking DB layer
- DB fixtures via factory functions or fixtures — never hardcode test data inline
- Reset strategy between tests: transaction rollback (preferred) or truncate

## Structure
- Tests mirror source: `src/users/service.py` → `tests/unit/users/test_service.py`
- Separate: unit (pure logic), integration (real DB/filesystem), e2e (full HTTP stack)
- Shared fixtures in conftest.py (Python) or fixtures/ directory (JS/TS)
- Test file imports explicit — no wildcard imports

## Running Tests
- Check agent_docs/testing.md for exact commands
- Always run full suite before considering any task complete
- Flaky tests are bugs — fix or delete, never skip permanently
- Coverage target: minimum 80% line coverage on new code; enforce in CI, not just locally
- CI gate: full test suite must pass before any merge to main
