from __future__ import annotations
import os
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func, create_engine
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/red_team")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class FraudGenomeRecord(Base):
    __tablename__ = "fraud_genomes"

    genome_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    lineage_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    parent_genome_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("fraud_genomes.genome_id"), nullable=True
    )
    generation: Mapped[int] = mapped_column(Integer, default=0)
    topology: Mapped[dict] = mapped_column(JSONB, nullable=False)
    timing: Mapped[dict] = mapped_column(JSONB, nullable=False)
    amounts: Mapped[dict] = mapped_column(JSONB, nullable=False)
    channels: Mapped[dict] = mapped_column(JSONB, nullable=False)
    accounts: Mapped[dict] = mapped_column(JSONB, nullable=False)
    special_nodes: Mapped[dict] = mapped_column(JSONB, nullable=False)
    mutation_history: Mapped[list] = mapped_column(JSONB, default=list)
    fitness_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    realism_score: Mapped[float] = mapped_column(Float, default=0.0)
    novelty_score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    flags: Mapped[list] = mapped_column(JSONB, default=list)
    repair_recommendation: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LineageScore(Base):
    __tablename__ = "lineage_scores"

    lineage_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    seed_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    total_predictions: Mapped[int] = mapped_column(Integer, default=0)
    confirmed_hits: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_hit_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def hit_rate(self) -> float:
        if self.total_predictions == 0:
            return 0.0
        return self.confirmed_hits / self.total_predictions


class ProphecyLedgerRecord(Base):
    __tablename__ = "prophecy_ledger"

    prediction_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    genome_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("fraud_genomes.genome_id"), nullable=False
    )
    lineage_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    prediction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    match_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    human_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    repair_recommendation: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    matched: Mapped[bool] = mapped_column(Boolean, default=False)
    match_count: Mapped[int] = mapped_column(Integer, default=0)
    ledger_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConfirmedFraud(Base):
    __tablename__ = "confirmed_frauds"

    fraud_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    confirmed_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmation_method: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    fraud_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    accounts_involved: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    amount_total: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    topology: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    timing: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    amounts_info: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    channels_info: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    accounts_info: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    ingested_into_prophecy: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProphecyMatch(Base):
    __tablename__ = "prophecy_matches"

    match_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    prediction_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("prophecy_ledger.prediction_id"), nullable=False
    )
    fraud_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("confirmed_frauds.fraud_id"), nullable=False
    )
    lineage_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    match_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    days_ahead: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OperatorPerformance(Base):
    __tablename__ = "operator_performance"

    operator_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    total_applied: Mapped[int] = mapped_column(Integer, default=0)
    hit_contribution: Mapped[int] = mapped_column(Integer, default=0)
    current_weight: Mapped[float] = mapped_column(Float, default=1.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class HumanGateQueueRecord(Base):
    __tablename__ = "human_gate_queue"

    queue_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    genome_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("fraud_genomes.genome_id"), nullable=False
    )
    impact_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    novelty_score: Mapped[float] = mapped_column(Float, default=0.0)
    realism_score: Mapped[float] = mapped_column(Float, default=0.0)
    lineage_trust: Mapped[float] = mapped_column(Float, default=0.0)
    autonomy_level: Mapped[str] = mapped_column(String(20), default="new")  # new | proven | highly_proven
    repair_recommendation: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | reviewed | executed
    review_1_investigator: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    review_1_decision: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    review_1_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    review_2_investigator: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    review_2_decision: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    review_2_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    final_decision: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    final_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
