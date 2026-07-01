"""
TGiE Adversarial Ecosystem
==========================

A coupled Red Team ⇄ Blue Team self-play system whose purpose is to make the
Blue Team (TGiE fraud detector) progressively more robust by exposing it to
sophisticated, evolving graph attacks.

This package is intentionally SEPARATE from the legacy ``red_team/`` package,
which enforces a hard import-time isolation contract (no coupling to the
detector). Here, coupling is the entire point: the Red Team observes the Blue
Team, learns its weaknesses, and the discovered hard examples are fed back to
harden the defender.

Design grounded in:  adversarial/reports/BLUE_TEAM_WHITEBOX_REPORT.md

Layout
------
    common/        attack-graph representation, objective, distortion, BlueTeam oracle
    red_team/      graph generator + attack agents + evolutionary engine (+ RL, GAN)
    self_play/     the AlphaGo-style Blue⇄Red loop (scaffold)
    attack_memory/ persistence of successful attacks + genealogy (scaffold)
    curriculum/    L1–L10 difficulty ladder (scaffold)
    evaluation/    metrics: ASR, stealth, distortion, robustness gain, ...
    visualization/ dashboards (scaffold)
    experiments/   reproducible runs
"""

__version__ = "0.1.0"
