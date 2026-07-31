"""Canonical investigation data model (ERH26_PS_03).

Single fusion target that every parser maps into. Implements the model defined in
`research/06_data_understanding.md` §4 and the entity list in the build master prompt:
Entity, EntityIdentifier, Event (TRANSACTION | CALL | IP_SESSION), and EntityLink.

Design principles (traceable to requirements):
- FR-6/FR-7: one entity + one time model for all sources.
- FR-10: identifiers are first-class so entities can be linked via shared IDs.
- NFR-7: every Event carries an immutable `provenance` block (source file/row).
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


class EntityType(str, enum.Enum):
    PERSON = "PERSON"
    ACCOUNT = "ACCOUNT"
    PHONE = "PHONE"
    IP = "IP"
    UNKNOWN = "UNKNOWN"


class IdentifierType(str, enum.Enum):
    ACCOUNT_NO = "ACCOUNT_NO"
    PHONE = "PHONE"
    IP = "IP"
    UPI_ID = "UPI_ID"
    IMEI = "IMEI"
    IMSI = "IMSI"
    BENEFICIARY = "BENEFICIARY"


class SourceType(str, enum.Enum):
    BANK = "BANK"
    CDR = "CDR"
    IPDR = "IPDR"


class EventType(str, enum.Enum):
    TRANSACTION = "TRANSACTION"
    CALL = "CALL"
    IP_SESSION = "IP_SESSION"


class Direction(str, enum.Enum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"
    IN = "IN"
    OUT = "OUT"


class LinkType(str, enum.Enum):
    MONEY_FLOW = "MONEY_FLOW"
    COMMUNICATION = "COMMUNICATION"
    SHARED_IDENTIFIER = "SHARED_IDENTIFIER"


class Entity(Base):
    """A resolved real-world actor (connected component of identifiers) — Doc 06 §4.1."""

    __tablename__ = "entity"

    pk = Column(Integer, primary_key=True, autoincrement=True)
    dataset = Column(String, nullable=False, index=True)   # scope rows by dataset/case
    entity_id = Column(String, nullable=False, index=True)
    entity_type = Column(String, nullable=False, default=EntityType.UNKNOWN.value)
    display_label = Column(String, nullable=True)
    risk_score = Column(Float, nullable=True)  # populated after detection (FR-12)
    oversized = Column(String, nullable=True)  # C3 circuit-breaker flag

    __table_args__ = (Index("ix_entity_dataset_eid", "dataset", "entity_id"),)


class EntityIdentifier(Base):
    """A single identifier belonging to an entity — Doc 06 §4.2 (supports FR-10 linkage)."""

    __tablename__ = "entity_identifier"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset = Column(String, nullable=False, index=True)
    entity_id = Column(String, nullable=False)
    id_type = Column(String, nullable=False)
    id_value = Column(String, nullable=False)

    __table_args__ = (
        Index("ix_identifier_type_value", "id_type", "id_value"),
    )


class Event(Base):
    """The unified timeline record — Doc 06 §4.3.

    One row per parsed source record, normalized. Type-specific fields live in
    `attributes` (JSON); `provenance` preserves the origin for evidentiary trust (NFR-7).
    """

    __tablename__ = "event"

    event_id = Column(String, primary_key=True, default=_uuid)
    dataset = Column(String, nullable=False, index=True)
    event_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=True)
    counterparty_entity_id = Column(String, nullable=True)

    timestamp_start = Column(DateTime(timezone=True), nullable=False)
    timestamp_end = Column(DateTime(timezone=True), nullable=True)

    amount = Column(Numeric(18, 2), nullable=True)  # transactions
    direction = Column(String, nullable=True)

    attributes = Column(JSON, nullable=False, default=dict)
    provenance = Column(JSON, nullable=False, default=dict)  # {source_file, sheet, row, offset, profile}

    __table_args__ = (
        Index("ix_event_entity_time", "dataset", "entity_id", "timestamp_start"),
        Index("ix_event_type_time", "dataset", "event_type", "timestamp_start"),
    )


class EntityLink(Base):
    """An edge in the investigation graph — Doc 06 §4.4 (money-flow / comms / shared-id)."""

    __tablename__ = "entity_link"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset = Column(String, nullable=False, index=True)
    from_entity_id = Column(String, nullable=False)
    to_entity_id = Column(String, nullable=False)
    link_type = Column(String, nullable=False)
    amount = Column(Numeric(18, 2), nullable=True)
    weight = Column(Float, nullable=False, default=1.0)

    __table_args__ = (
        Index("ix_link_from_to", "dataset", "from_entity_id", "to_entity_id"),
    )


class RiskAssessment(Base):
    """Persisted per-entity risk result (FR-12) with contributing factors (NFR-7)."""

    __tablename__ = "risk_assessment"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset = Column(String, nullable=False, index=True)
    entity_id = Column(String, nullable=False)
    label = Column(String, nullable=True)
    risk_score = Column(Float, nullable=False)
    band = Column(String, nullable=False)
    ml_score = Column(Float, nullable=True)
    #: Whether `ml_score` is a measurement or an absence. The Isolation Forest is fitted only on
    #: entities holding records of their own, and min-max normalisation also assigns 0.0 to the
    #: least anomalous fitted entity — so a persisted 0.0 alone cannot tell "examined, not
    #: anomalous" from "never had a profile to examine". Nullable because rows written before
    #: this column existed genuinely do not know which they were.
    ml_scored = Column(Boolean, nullable=True)
    rule_flags = Column(JSON, nullable=False, default=list)


class CorrelationHitRow(Base):
    """Persisted call+IP+transfer coincidence (FR-9) with evidence + provenance (NFR-7)."""

    __tablename__ = "correlation_hit"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset = Column(String, nullable=False, index=True)
    entity_id = Column(String, nullable=True)
    entity_label = Column(String, nullable=True)
    window_minutes = Column(Integer, nullable=False)
    explanation = Column(String, nullable=True)
    evidence = Column(JSON, nullable=False, default=dict)
