#!/usr/bin/env python3
"""
UB mock interview — fire a hostile / cross-examination question set at the running
UB service and print its answers, so you can stress-test how UB holds up under tough
judge-style questioning before a real demo.

Usage:
    python ub/scripts/mock_interview.py                 # all questions, judge mode
    python ub/scripts/mock_interview.py -n 8            # first 8 only
    python ub/scripts/mock_interview.py --mode developer
    python ub/scripts/mock_interview.py --host http://localhost:8001

Requires the UB service running (control/start_tgie.command, or
`cd backend && PYTHONPATH=backend <venv-py> -m ub_service`). Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

# A deliberately tough, broad set — facts, internals, and hostile cross-exam.
QUESTIONS = [
    "What problem does TGIE solve and why is the graph the right abstraction?",
    "How does Blue Team V2 score a node and what are the thresholds?",
    "Does the Red Team automatically train the Blue Team? Explain the workflow.",
    "How does TGIE handle cash deposits and withdrawals, and what color are the cash nodes?",
    "What is the production readiness score and how is it derived?",
    "Which model does UB run, why that one, and how fast is it?",
    "What's your benign false-positive rate and why should I trust this?",
    "How do I know your results aren't overfit to your own synthetic data?",
    "What in this demo is real versus synthetic or faked?",
    "If I fragment my laundering into tiny pieces, don't you miss it?",
    "Can't an attacker just read your fixed thresholds and evade them?",
    "Isn't this just a graph visualization with a fraud label on it?",
    "What are the context signals and how does the arms race end?",
    "How effective is the account-takeover attack, specifically?",
    "What attacks have you NOT done — be honest about coverage gaps.",
    "Why a local LLM instead of a cloud model like GPT-4?",
    "Why should a bank pick this over an existing AML vendor?",
    "What's the single weakest part of the whole system?",
    "Why did the 3D graph look like a rhombus, and is it fixed?",
    "Did you just hardcode the demo answers?",
]


def ask(host: str, mode: str, question: str, timeout: int = 120) -> dict:
    body = json.dumps({"message": question}).encode()
    req = urllib.request.Request(
        f"{host}/ub/{mode}", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="UB hostile mock interview")
    ap.add_argument("--host", default="http://localhost:8001")
    ap.add_argument("--mode", default="judge",
                    choices=["judge", "chat", "developer", "presentation", "founder"])
    ap.add_argument("-n", "--num", type=int, default=len(QUESTIONS),
                    help="how many questions to ask")
    args = ap.parse_args(argv)

    qs = QUESTIONS[: max(1, args.num)]
    print(f"\n=== UB MOCK INTERVIEW · {args.mode} mode · {len(qs)} questions · {args.host} ===\n")
    t0 = time.time()
    for i, q in enumerate(qs, 1):
        print(f"\033[1m[{i:>2}/{len(qs)}] Q: {q}\033[0m")
        try:
            res = ask(args.host, args.mode, q)
            answer = res.get("answer", "(no answer field)")
            srcs = res.get("sources") or []
            print(f"    A: {answer.strip()}")
            if srcs:
                cited = ", ".join(s.get("path", "?") for s in srcs[:3])
                print(f"    \033[2msources: {cited}\033[0m")
        except Exception as e:  # noqa: BLE001
            print(f"    \033[31m! UB error: {e}\033[0m  (is the UB service up on {args.host}?)")
            return 1
        print()
    print(f"=== done in {time.time() - t0:.0f}s ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
