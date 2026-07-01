"""
Adversarial governance — Training Queue + audit + dedup tests.

Asserts the human-in-the-loop invariants:
  • Only Blue MISSES (real on-graph evasions) enter the queue; detected/garbage don't.
  • Nothing reaches the Blue Knowledge Base without an explicit 'learn' decision.
  • Duplicate signatures merge instead of creating a second KB entry.
  • Every decision is written to the audit trail.

Runs WITHOUT pytest:  python backend/tests/test_training_governance.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Isolate persistence to a temp file so tests never touch real data.
os.environ["TGIE_TRAINING_STORE"] = os.path.join(tempfile.mkdtemp(), "tq.json")

from adversarial_governance.store import GovernanceStore, PENDING, LEARNED, REJECTED  # noqa: E402


def _cand(cid, archetype="smurfing", techniques=("amount_dither", "decoy_edges"),
          risk=0.12, blue_catches=False, trainable=True):
    return {
        "id": cid, "archetype": archetype, "techniques": list(techniques),
        "graph": {"nodes": [], "edges": []}, "nodes_total": 10, "edges_total": 12,
        "native": {"verdict": "CLEAN", "risk": risk, "evaded": True},
        "hardened": {"verdict": "FRAUD", "risk": 0.8, "caught": True, "signal": "provenance"},
        "reason": "on-graph & objective intact — a real evasion",
        "blue_catches": blue_catches, "trainable": trainable,
    }


def _fresh():
    # The store's data-file path is fixed at import, so a new instance reuses the
    # same temp file; reset() guarantees each test starts from a clean slate.
    s = GovernanceStore()
    s.reset()
    return s


def test_only_misses_enqueue():
    s = _fresh()
    assert s.enqueue(_cand("0:smurf")) is not None, "a real Blue miss is queued"
    # Blue already catches → not a learning case
    assert s.enqueue(_cand("0:fanout", blue_catches=True)) is None, "detected attack not queued"
    # not trainable (garbage) → not queued
    assert s.enqueue(_cand("0:junk", trainable=False)) is None, "garbage not queued"
    assert s.stats()["pending"] == 1


def test_enqueue_is_idempotent():
    s = _fresh()
    a = s.enqueue(_cand("0:smurf"))
    b = s.enqueue(_cand("0:smurf"))            # same candidate id again
    assert a["case_id"] == b["case_id"], "re-enqueue returns the same case (no dupes)"
    assert s.stats()["total"] == 1


def test_nothing_learns_without_decision():
    s = _fresh()
    s.enqueue(_cand("0:smurf"))
    assert s.stats()["knowledge_base"] == 0, "queue alone never touches the knowledge base"


def test_learn_adds_to_knowledge_and_audits():
    s = _fresh()
    c = s.enqueue(_cand("0:smurf"))
    res = s.decide(c["case_id"], "learn", investigator="alice")
    assert res["ok"] and res["case"]["status"] == LEARNED
    assert s.stats()["knowledge_base"] == 1, "new pattern added to KB"
    audit = s.audit()
    assert any(a["decision"] == "learn" and a["investigator"] == "alice"
               and a["training_status"] == "Added to Blue Knowledge Base" for a in audit), "learn audited"


def test_duplicate_signature_merges():
    s = _fresh()
    c1 = s.enqueue(_cand("0:smurf", techniques=("amount_dither", "decoy_edges")))
    s.decide(c1["case_id"], "learn")
    # different candidate id, SAME fraud type + technique set → same signature
    c2 = s.enqueue(_cand("1:smurf", techniques=("decoy_edges", "amount_dither")))
    res = s.decide(c2["case_id"], "learn")
    assert res["dedup"]["merged_into"] == c1["case_id"], "merged into the existing KB entry"
    assert res["dedup"]["count"] == 2
    assert s.stats()["knowledge_base"] == 1, "no second KB entry created"


def test_reject_discards():
    s = _fresh()
    c = s.enqueue(_cand("0:smurf"))
    s.decide(c["case_id"], "reject", investigator="bob")
    assert s.get(c["case_id"])["status"] == REJECTED
    assert s.stats()["knowledge_base"] == 0, "rejected case never enters KB"


def test_similar_detection():
    s = _fresh()
    a = s.enqueue(_cand("0:smurf", techniques=("amount_dither", "decoy_edges")))
    s.enqueue(_cand("1:smurf", techniques=("amount_dither", "relay_insertion")))  # same type, overlap
    sim = s.similar(a["case_id"])
    assert len(sim) >= 1, "finds a similar same-type case"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        try:
            t(); print(f"  PASS  {t.__name__}"); passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}"); failed += 1
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}"); failed += 1
    print(f"\n{passed} passed, {failed} failed, {len(tests)} total")
    sys.exit(1 if failed else 0)
