"""
CRUCIBLE Intelligent Fraud Evolution Engine.

A controlled, investigator-in-control adversarial simulation that continuously
evolves synthetic fraud against Blue Team V2 to surface blind spots — strictly a
defensive research simulator on synthetic data. The Red Team NEVER auto-trains
Blue: successful (missed) attacks become investigator alerts, and only an
approved alert reaches the hardening backlog (see learning_gate).

Public surface:
    EvolutionEngine            — the orchestrator (run_attack / run_campaign)
    library.FAMILIES           — the attack library
    weakness.WeaknessMap       — Blue weakness discovery + planner
    learning_gate.learning_gate — investigator approval boundary
"""
from red_team.evolution.engine import AttackRun, EvolutionEngine, Generation
from red_team.evolution.llm_strategist import EvasionPlan, LLMStrategist
from red_team.evolution.strategy_memory import Strategy, StrategyMemory

__all__ = ["EvolutionEngine", "AttackRun", "Generation",
           "LLMStrategist", "EvasionPlan", "StrategyMemory", "Strategy"]
