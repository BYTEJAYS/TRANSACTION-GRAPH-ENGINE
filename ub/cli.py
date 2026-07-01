"""
UB command-line interface.

  python -m ub status                 # hardware/model/index health
  python -m ub index                  # (re)build summaries + knowledge index
  python -m ub summaries              # regenerate the 5 summary JSONs only
  python -m ub ask "question" [-m developer]
  python -m ub chat [-m founder]      # interactive multi-turn REPL
  python -m ub demo                   # auto-present TGIE end to end
  python -m ub benchmark              # benchmark installed chat models
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid

from .ollama_service import OllamaClient, FAST_CHAT_MODEL  # type: ignore
from .ollama_service.client import DEFAULT_CHAT_MODEL
from .knowledge_engine import KnowledgeEngine
from .knowledge_engine.summarizer import generate_all
from .ai_core import UBBrain, modes


def _brain() -> UBBrain:
    return UBBrain(auto_refresh=False)


def cmd_status(_args) -> None:
    b = _brain()
    print(json.dumps(b.context_report(), indent=2))


def cmd_summaries(_args) -> None:
    written = generate_all()
    print("summaries written:", ", ".join(written))


def cmd_index(_args) -> None:
    print("[ub] regenerating project summaries ...")
    generate_all()
    print("[ub] building knowledge index (embeds every TGIE chunk locally) ...")
    meta = KnowledgeEngine().build(verbose=True)
    print(json.dumps({k: v for k, v in meta.items() if k != "manifest"}, indent=2))


def cmd_ask(args) -> None:
    res = _brain().ask(args.question, mode=args.mode, session_id=args.session)
    print(res["answer"])
    if res["sources"]:
        print("\n— sources —")
        for s in res["sources"][:6]:
            print(f"  {s['component']} · {s['path']}:{s['lines']} (rel={s['score']})")


def cmd_chat(args) -> None:
    b = _brain()
    sid = args.session or f"cli-{uuid.uuid4().hex[:8]}"
    print(f"UB ready · mode={args.mode} · model={b.client.model} · session={sid}")
    print("type your question (':mode developer' to switch, ':quit' to exit)\n")
    mode = args.mode
    while True:
        try:
            msg = input("you › ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye."); break
        if not msg:
            continue
        if msg in (":quit", ":q", "exit"):
            break
        if msg.startswith(":mode "):
            mode = msg.split(" ", 1)[1].strip()
            print(f"[mode → {mode}]"); continue
        print("UB  › ", end="", flush=True)
        try:
            for tok in b.ask_stream(msg, mode=mode, session_id=sid):
                sys.stdout.write(tok); sys.stdout.flush()
            print("\n")
        except Exception as e:
            print(f"[error] {e}\n")


def cmd_demo(args) -> None:
    b = _brain()
    sid = args.session or f"demo-{uuid.uuid4().hex[:6]}"
    for sec in b.demo(session_id=sid):
        print("\n" + "=" * 70)
        print(f"▌ {sec['section']}")
        print("=" * 70)
        print(sec["content"])


def cmd_benchmark(_args) -> None:
    c = OllamaClient()
    health = c.health()
    candidates = [m for m in (DEFAULT_CHAT_MODEL, FAST_CHAT_MODEL) if m in health.get("models", [])]
    print(f"benchmarking: {candidates}\n")
    for m in candidates:
        print(json.dumps(c.benchmark(model=m), indent=2))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="ub", description="UB — TGIE Universal Brain")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("summaries").set_defaults(func=cmd_summaries)
    sub.add_parser("index").set_defaults(func=cmd_index)
    sub.add_parser("benchmark").set_defaults(func=cmd_benchmark)

    a = sub.add_parser("ask"); a.add_argument("question")
    a.add_argument("-m", "--mode", default="chat", choices=list(modes.MODES))
    a.add_argument("-s", "--session", default=None); a.set_defaults(func=cmd_ask)

    c = sub.add_parser("chat")
    c.add_argument("-m", "--mode", default="chat", choices=list(modes.MODES))
    c.add_argument("-s", "--session", default=None); c.set_defaults(func=cmd_chat)

    d = sub.add_parser("demo"); d.add_argument("-s", "--session", default=None)
    d.set_defaults(func=cmd_demo)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
