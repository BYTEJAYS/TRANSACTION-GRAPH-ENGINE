"""
UB recovery client — turns a Recovery Probability analysis into a plain-banking
explanation via the local Ollama model, with a deterministic fallback so the
platform never blocks on the LLM.
"""
from __future__ import annotations

import os
from typing import Optional

import httpx

OLLAMA_URL = os.getenv("TGIE_OLLAMA_URL", "http://localhost:11434")
UB_MODEL = os.getenv("TGIE_UB_MODEL", "llama3.1:8b")
_TIMEOUT = float(os.getenv("TGIE_UB_TIMEOUT", "30"))


def _inr(v: float) -> str:
    if v >= 1e7:
        return f"₹{v / 1e7:.2f} Cr"
    if v >= 1e5:
        return f"₹{v / 1e5:.2f} L"
    return f"₹{int(v):,}"


def build_prompt(analysis: dict, question: Optional[str] = None) -> str:
    f = {x["key"]: x for x in analysis["factors"]}
    factor_lines = "\n".join(f"  - {x['name']}: {x['score']}/100 ({x['label']})" for x in analysis["factors"])
    acts = analysis["actions"][:3]
    act_lines = "\n".join(
        f"  - P{a['priority']} {a['action']} (impact {a['impact']}, +{a['expected_recovery_increase']}% recovery)"
        for a in acts
    ) or "  - none"
    crit = analysis.get("critical_accounts") or []
    crit_line = (f"{crit[0]['account']} holding {crit[0]['freeze_impact']}% of recoverable funds"
                 if crit else "none identified")
    q = question or "Explain the recovery outlook and the single most important next action."
    return (
        "You are UB, the AI fraud-recovery analyst inside TGIE, a bank fraud operations "
        "platform. Speak to a bank manager in plain, professional banking language — no "
        "markdown, no bullet points, no preamble.\n\n"
        f"CASE {analysis['case_id']} — {analysis['title']} ({analysis.get('category')})\n"
        f"Recovery probability: {analysis['recovery_probability']}% ({analysis['band']}), "
        f"confidence {analysis['confidence']}%.\n"
        f"Of {_inr(analysis['funnel']['fraud_amount'])} originally moved, "
        f"{_inr(analysis['expected_recoverable'])} is realistically recoverable; "
        f"projected loss {_inr(analysis['estimated_loss'])}.\n"
        f"Critical account: {crit_line}.\n"
        f"Recovery factors (0-100, higher = better):\n{factor_lines}\n\n"
        f"Top recommended actions:\n{act_lines}\n\n"
        f"QUESTION: {q}\n\n"
        "Answer in 3-5 sentences: state whether the money can realistically be recovered "
        "and why (cite the deciding factors), how much and how fast, and the single most "
        "important action to take now. Be concrete and decisive."
    )


async def llm_answer(prompt: str) -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": UB_MODEL, "prompt": prompt, "stream": False,
                      "options": {"temperature": 0.4, "num_predict": 300}},
            )
            if r.status_code != 200:
                return None
            return (r.json().get("response") or "").strip() or None
    except Exception:
        return None


def heuristic_answer(analysis: dict, question: Optional[str] = None) -> str:
    crit = analysis.get("critical_accounts") or []
    wf = next((x for x in analysis["factors"] if x["key"] == "withdrawal"), {})
    lead = analysis["actions"][0] if analysis["actions"] else None
    parts = [
        f"Recovery probability is {analysis['recovery_probability']}% — {analysis['band'].lower()} — "
        f"at {analysis['confidence']}% confidence.",
        f"Of {_inr(analysis['funnel']['fraud_amount'])} originally moved, about "
        f"{_inr(analysis['expected_recoverable'])} is realistically recoverable "
        f"(projected loss {_inr(analysis['estimated_loss'])}).",
    ]
    if wf:
        parts.append(wf["label"] + ".")
    if lead:
        parts.append(f"Act first on: {lead['action']} ({lead['rationale']})")
    if crit:
        parts.append(f"Freezing {crit[0]['account']} alone preserves {crit[0]['freeze_impact']}% of recoverable funds.")
    return " ".join(parts)
