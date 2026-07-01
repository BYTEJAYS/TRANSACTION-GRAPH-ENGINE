"""Redirect the learning-gate durable stores to a temp dir for the test session,
so running tests never pollutes the repo's evolution/data directory."""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="crucible_test_")
os.environ.setdefault("CRUCIBLE_ALERTS_STORE", os.path.join(_tmp, "alerts.jsonl"))
os.environ.setdefault("CRUCIBLE_HARDENING_BACKLOG", os.path.join(_tmp, "backlog.jsonl"))
os.environ.setdefault("CRUCIBLE_STRATEGY_MEMORY", os.path.join(_tmp, "strategy.jsonl"))
