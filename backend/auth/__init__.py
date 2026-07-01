"""
TGIE Investigator Authentication & Account Intelligence module.

Self-contained, zero extra dependencies (stdlib only):
  - security.py      JWT (HMAC-SHA256) + PBKDF2 password hashing
  - store.py         investigator directory, lockout, sessions, audit log
  - accounts_db.py   synthetic account / case / evidence registry for search
  - router.py        FastAPI endpoints + require_auth dependency

Mounted in main.py under /api/auth, /api/accounts, /api/investigator.
"""

from .router import router as auth_router  # noqa: F401
