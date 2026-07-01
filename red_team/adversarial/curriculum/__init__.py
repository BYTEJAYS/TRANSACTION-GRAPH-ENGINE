"""Curriculum Learning — the L1–L10 difficulty ladder for self-play."""
from .ladder import LADDER, CurriculumLevel, level, allowed_agents

__all__ = ["LADDER", "CurriculumLevel", "level", "allowed_agents"]
