"""Self-Play — the AlphaGo-style Blue⇄Red hardening loop (interfaces + scaffold)."""
from .loop import SelfPlayLoop, BlueTeamHardener, ThresholdHardener

__all__ = ["SelfPlayLoop", "BlueTeamHardener", "ThresholdHardener"]
