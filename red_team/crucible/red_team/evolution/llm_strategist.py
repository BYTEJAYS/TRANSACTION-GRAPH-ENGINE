from __future__ import annotations
"""
LLM Adversarial Strategist — the Ollama-powered Red Team brain.

Given Blue Team V2's verdict (which detectors fired and why), the current genome,
and the most relevant past wins, a local LLM proposes a smarter, harder-to-detect
reshaping: which mutation operators to apply AND direct gene overrides (channels,
timing, amounts, ages, topology). This goes beyond the static detector→operator map
— the model can reason about combinations and invent evasions the heuristics miss.

Safety / scope:
  • Red-only. The strategist NEVER calls or imports Blue Team; it only reads a text
    summary of Blue's verdict (which Red already has) and proposes RED mutations.
  • Untrusted output. The LLM is a generator, not an authority: every field it
    returns is strictly validated/clamped against the LOCKED transaction format
    (9 rails, integer amounts, valid enums) before anything is applied. Unknown keys
    are ignored; invalid values are dropped. Nothing is ever eval'd.
  • Optional. If Ollama is down or returns junk, `propose()` returns None and the
    engine falls back to the deterministic heuristic mutation. No hard dependency.
"""
import copy
import logging
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from red_team.core.rail_constraints import RAIL_LIMITS
from red_team.evolution.llm_client import DEFAULT_MODEL, OllamaClient, OllamaError
from red_team.mutation.operators import ALL_OPERATORS

if TYPE_CHECKING:
    from red_team.core.genome import FraudGenome
    from red_team.evolution.failure_analysis import FailureReport
    from red_team.evolution.strategy_memory import Strategy

logger = logging.getLogger(__name__)

_VALID_RAILS = frozenset(RAIL_LIMITS)                       # the 9 locked rails
_VALID_OPS = frozenset(op.__name__ for op in ALL_OPERATORS)  # 25 mutation operators
_OPS_BY_NAME = {op.__name__: op for op in ALL_OPERATORS}
_VALID_TOD = frozenset({"business_hours", "morning", "afternoon", "evening", "night"})
_VALID_PATTERN = frozenset({"equal_split", "organic_noisy", "decreasing", "increasing"})
_VALID_TOPO = frozenset({"fan_in", "fan_out", "bipartite", "chain", "cycle"})

# Blue Team V2's detector catalogue — given to the model so it knows what to dodge.
_DETECTORS = ("fan_in fan_out smurfing mule_accounts bridge_accounts dormant_accounts "
              "circular_flow layering cashout velocity synthetic_networks hybrid_network")

_SYSTEM = (
    "You are an adversarial fraud-pattern STRATEGIST inside a DEFENSIVE red-team "
    "SIMULATION that stress-tests a bank's fraud-detection system on SYNTHETIC data. "
    "Your job: redesign a synthetic fraud 'genome' so the detectors stop firing while "
    "the pattern still looks like realistic banking activity. This improves the "
    "defender. Reply with STRICT JSON only — no prose outside the JSON object."
)


@dataclass
class EvasionPlan:
    reasoning: str
    operators: list[str] = field(default_factory=list)
    gene_overrides: dict = field(default_factory=dict)
    model: str = ""
    latency_s: float = 0.0
    source: str = "llm"

    def to_dict(self) -> dict:
        return {"reasoning": self.reasoning, "operators": self.operators,
                "gene_overrides": self.gene_overrides, "model": self.model,
                "latency_s": self.latency_s, "source": self.source}


def _clampf(v, lo, hi, default=None):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return default


def _clampi(v, lo, hi, default=None):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


class LLMStrategist:
    """Wraps a local Ollama model as a validated mutation strategist."""

    def __init__(self, client: OllamaClient | None = None, model: str | None = None,
                 timeout: int = 60) -> None:
        self.client = client or OllamaClient(model=model or DEFAULT_MODEL, timeout=timeout)
        self.model = self.client.model
        self.calls = 0
        self.failures = 0
        self._health_cache: tuple[float, bool] | None = None

    def available(self) -> bool:
        """True iff Ollama is up and the model is pulled (cached 30s). Never raises."""
        import time
        now = time.time()
        if self._health_cache and now - self._health_cache[0] < 30:
            return self._health_cache[1]
        h = self.client.health()
        ok = bool(h.get("up") and h.get("model_available"))
        self._health_cache = (now, ok)
        return ok

    def status(self) -> dict:
        h = self.client.health()
        return {"model": self.model, "host": self.client.host, "up": h.get("up"),
                "model_available": h.get("model_available"),
                "available_models": h.get("models", []),
                "calls": self.calls, "failures": self.failures}

    # ── prompt construction ────────────────────────────────────────────────────
    def _build_user_prompt(self, genome_summary: dict, report: "FailureReport",
                           exemplars: list["Strategy"]) -> str:
        ex_txt = ""
        for s in exemplars:
            ex_txt += (f"\n- beat [{', '.join(s.beaten_detectors)}] via ops "
                       f"{s.operators} genes={s.gene_fingerprint}")
        return (
            f"BLUE TEAM V2 DETECTORS (avoid triggering these): {_DETECTORS}\n\n"
            f"CURRENT ATTACK (caught by Blue):\n"
            f"  topology={genome_summary.get('topology')} width={genome_summary.get('width')} "
            f"depth={genome_summary.get('depth')} total=₹{genome_summary.get('total_amount')}\n"
            f"  channels={genome_summary.get('channels')} time={genome_summary.get('time_of_day')}\n"
            f"  prior_mutations={genome_summary.get('mutation_history')}\n\n"
            f"BLUE FIRED: {report.triggered_detectors}\n"
            f"WHY: {report.causes}\n\n"
            f"AVAILABLE MUTATION OPERATORS (pick up to 4 by exact name):\n  {sorted(_VALID_OPS)}\n\n"
            f"HARD CONSTRAINTS (must respect):\n"
            f"  - payment rails MUST be from: {sorted(_VALID_RAILS)}\n"
            f"  - integer amounts; AVOID bands 49000-50000 / 99000-100000 / 990000-1000000\n"
            f"  - single-channel looks suspicious — diversify the channel mix\n"
            f"  - account ages > 200 days reduce the synthetic/dormant signal\n"
            f"  - slower velocity + timing spread over days looks more human\n"
            f"  - cash/crypto/ATM exits raise cashout risk; prefer layered digital rails\n"
            f"{('PAST WINS that beat similar detectors:' + ex_txt) if ex_txt else ''}\n\n"
            f"Return JSON: {{\n"
            f'  "reasoning": "<1-2 sentences>",\n'
            f'  "operators": ["<operator names from the menu>"],\n'
            f'  "gene_overrides": {{\n'
            f'     "channels": {{"<rail>": <weight 0..1>}},\n'
            f'     "spacing_days": [<float per gap>], "time_of_day": "<enum>", "low_slow": <bool>,\n'
            f'     "velocity_ratio": <0..1>, "source_age_min_days": <int>,\n'
            f'     "amount_pattern": "<equal_split|organic_noisy|decreasing|increasing>",\n'
            f'     "amount_scale": <0.2..3.0>, "topology_type": "<enum>",\n'
            f'     "topology_width": <int>, "topology_depth": <int>\n'
            f"  }}\n}}\n"
            f"Only include override keys you actually want to change."
        )

    # ── validation of untrusted LLM output ─────────────────────────────────────
    @staticmethod
    def _validate(obj: dict) -> EvasionPlan:
        reasoning = str(obj.get("reasoning", ""))[:400]
        ops = [o for o in obj.get("operators", []) if isinstance(o, str) and o in _VALID_OPS][:4]

        raw = obj.get("gene_overrides", {})
        ov: dict = {}
        if isinstance(raw, dict):
            ch = raw.get("channels")
            if isinstance(ch, dict):
                clean = {k: _clampf(v, 0.0, 1.0, 0.0) for k, v in ch.items()
                         if k in _VALID_RAILS and _clampf(v, 0.0, 1.0, 0.0) > 0}
                total = sum(clean.values())
                if total > 0:
                    ov["channels"] = {k: round(v / total, 4) for k, v in clean.items()}

            sp = raw.get("spacing_days")
            if isinstance(sp, list) and sp:
                clean_sp = [_clampf(x, 0.001, 365.0) for x in sp][:32]
                clean_sp = [x for x in clean_sp if x is not None]
                if clean_sp:
                    ov["spacing_days"] = clean_sp

            tod = raw.get("time_of_day")
            if tod in _VALID_TOD:
                ov["time_of_day"] = tod
            if isinstance(raw.get("low_slow"), bool):
                ov["low_slow"] = raw["low_slow"]

            vr = _clampf(raw.get("velocity_ratio"), 0.0, 1.0)
            if vr is not None and "velocity_ratio" in raw:
                ov["velocity_ratio"] = round(vr, 3)

            age = _clampi(raw.get("source_age_min_days"), 0, 3000)
            if age is not None and "source_age_min_days" in raw:
                ov["source_age_min_days"] = age

            if raw.get("amount_pattern") in _VALID_PATTERN:
                ov["amount_pattern"] = raw["amount_pattern"]
            sc = _clampf(raw.get("amount_scale"), 0.2, 3.0)
            if sc is not None and "amount_scale" in raw:
                ov["amount_scale"] = round(sc, 3)

            if raw.get("topology_type") in _VALID_TOPO:
                ov["topology_type"] = raw["topology_type"]
            tw = _clampi(raw.get("topology_width"), 1, 40)
            if tw is not None and "topology_width" in raw:
                ov["topology_width"] = tw
            td = _clampi(raw.get("topology_depth"), 1, 12)
            if td is not None and "topology_depth" in raw:
                ov["topology_depth"] = td

        return EvasionPlan(reasoning=reasoning, operators=ops, gene_overrides=ov)

    # ── public: propose ────────────────────────────────────────────────────────
    def propose(self, genome_summary: dict, report: "FailureReport",
                exemplars: list["Strategy"] | None = None) -> EvasionPlan | None:
        if not self.available():
            return None
        user = self._build_user_prompt(genome_summary, report, exemplars or [])
        try:
            obj = self.client.chat_json(_SYSTEM, user)
            self.calls += 1
        except OllamaError as exc:
            self.failures += 1
            logger.warning("LLM strategist call failed: %s", exc)
            return None
        plan = self._validate(obj)
        plan.model = self.model
        plan.latency_s = float(obj.get("_latency_s", 0.0))
        if not plan.operators and not plan.gene_overrides:
            return None  # nothing usable → let the heuristic drive
        return plan

    # ── public: apply (within locked format) ───────────────────────────────────
    def apply(self, genome: "FraudGenome", plan: EvasionPlan, realism) -> tuple["FraudGenome", dict]:
        """Apply a validated plan to a genome clone. Reverts overrides if they break
        hard validation; always returns a structurally valid genome."""
        base = copy.deepcopy(genome)
        applied = {"operators": [], "gene_overrides": {}}

        # 1) operators (reuse the real registry)
        g = base
        for name in plan.operators:
            op = _OPS_BY_NAME.get(name)
            if op is None:
                continue
            try:
                g = op(g)
                applied["operators"].append(name)
            except Exception:
                continue

        pre_override = copy.deepcopy(g)

        # 2) gene overrides (already validated/clamped)
        ov = plan.gene_overrides
        if "channels" in ov:
            g.channels.mix = dict(ov["channels"])
            g.channels.channel_sequence = []
        if "spacing_days" in ov:
            g.timing.spacing_days = list(ov["spacing_days"])
        if "time_of_day" in ov:
            g.timing.time_of_day = ov["time_of_day"]
        if "low_slow" in ov:
            g.timing.low_slow = ov["low_slow"]
        if "velocity_ratio" in ov:
            g.accounts.velocity_ratio = ov["velocity_ratio"]
        if "source_age_min_days" in ov:
            floor = ov["source_age_min_days"]
            g.accounts.source_ages_days = [max(int(a), floor)
                                           for a in (g.accounts.source_ages_days or [floor])]
        if "amount_pattern" in ov:
            g.amounts.pattern = ov["amount_pattern"]
        if "amount_scale" in ov:
            g.amounts.values = [_dethreshold(int(a * ov["amount_scale"]))
                                for a in g.amounts.values] or g.amounts.values
        if "topology_type" in ov:
            g.topology.type = ov["topology_type"]
        if "topology_width" in ov:
            g.topology.width = ov["topology_width"]
        if "topology_depth" in ov:
            g.topology.depth = ov["topology_depth"]
        applied["gene_overrides"] = dict(ov)

        # 3) keep it valid — revert overrides (not operators) if they broke realism
        valid, _ = realism.hard_validate(g)
        if not valid:
            g = pre_override
            applied["gene_overrides"] = {"reverted": True}

        # 4) lineage bookkeeping
        g.genome_id = str(uuid.uuid4())
        g.parent_genome_id = genome.genome_id
        g.generation = genome.generation + 1
        for tag in (["llm_strategist"] + applied["operators"]):
            if tag not in g.mutation_history:
                g.mutation_history.append(tag)
        return g, applied


_THRESHOLD_BANDS = ((49_000, 50_000), (99_000, 100_000), (990_000, 1_000_000))


def _dethreshold(amount: int) -> int:
    """Nudge an amount out of a reporting band so it doesn't hand Blue a free flag."""
    amount = max(100, min(amount, 9_999_999))
    for lo, hi in _THRESHOLD_BANDS:
        if lo <= amount < hi:
            return lo - 1
    return amount
