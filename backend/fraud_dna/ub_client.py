"""
UB (Universal Brain) client — turns a case's Fraud-DNA into a natural-language
explanation using the live local Ollama model (same model the UB service uses).

Falls back silently to the deterministic heuristic explanation when Ollama is
unreachable, so the platform never blocks on the LLM being up.
"""

from __future__ import annotations

import os
from typing import List, Optional

import httpx

OLLAMA_URL = os.getenv("TGIE_OLLAMA_URL", "http://localhost:11434")
UB_MODEL = os.getenv("TGIE_UB_MODEL", "llama3.1:8b")
_TIMEOUT = float(os.getenv("TGIE_UB_TIMEOUT", "30"))


def build_prompt(case: dict, genes: List[dict], similar: dict) -> str:
    gene_lines = "\n".join(f"  - {g['name']}: {g['score']}/100 ({g['label']})" for g in genes)
    matches = similar.get("matches", [])[:3]
    match_lines = "\n".join(
        f"  - {m['case_id']} ({m['title']}): {m['similarity']}% — {', '.join(m['reasons'][:3])}"
        for m in matches
    ) or "  - none"
    pred = similar.get("prediction") or {}
    return (
        "You are UB, the AI fraud-investigation assistant inside TGIE, a bank fraud "
        "investigation platform. Explain a case's behavioural 'Fraud DNA' to a human "
        "investigator in plain, professional language.\n\n"
        f"CASE: {case['case_id']} — {case['title']} ({case['category']})\n"
        f"DNA type: {similar.get('dna_id', '')}\n"
        f"Risk score: {case.get('risk_score')}/100, priority {case.get('priority')}, status {case.get('status')}.\n\n"
        f"Behavioural genes (0-100):\n{gene_lines}\n\n"
        f"Most similar historical cases (behavioural match):\n{match_lines}\n\n"
        f"Prediction: pattern={pred.get('predicted_pattern')}, "
        f"escalation_probability={pred.get('escalation_probability')}%, "
        f"network_expansion={pred.get('expansion_probability')}%.\n\n"
        "Write 3-4 sentences for the investigator: what fraud methodology this DNA "
        "represents, which genes dominate and why that matters, what the strongest "
        "similar case implies, and one concrete recommended next step. Be specific and "
        "concise. No markdown, no bullet points, no preamble — just the explanation."
    )


async def llm_explain(prompt: str) -> Optional[str]:
    """Return an Ollama-generated explanation, or None if unavailable."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": UB_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.4, "num_predict": 260},
                },
            )
            if r.status_code != 200:
                return None
            text = (r.json().get("response") or "").strip()
            return text or None
    except Exception:
        return None


async def ollama_available() -> bool:
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            return r.status_code == 200
    except Exception:
        return False
