from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
)

from .base import metadata


# Immutable final page image for a successful handover / continuation batch.
page_snapshots = Table(
    "page_snapshots", metadata,
    Column("run_id", Integer, ForeignKey("runs.id"), primary_key=True),
    Column("capacity", Integer, nullable=False),
    Column("snapshot", JSON(none_as_null=True), nullable=False),
    Column("created_at", BigInteger, nullable=False),
)


# Durable state for night-shift continuation orders. The checkpoint is private
# until the whole order commits; it lets a recovered worker resume after a
# mid-order interruption without creating a second draft claim.
continuation_orders = Table(
    "continuation_orders", metadata,
    Column("run_id", Integer, ForeignKey("runs.id"), primary_key=True),
    Column("actor", String(48), nullable=False),
    Column("base_run_id", Integer, ForeignKey("runs.id"), nullable=False, index=True),
    Column("root_run_id", Integer, ForeignKey("runs.id"), nullable=False, index=True),
    Column("idempotency_key", String(128), nullable=True),
    Column("request_hash", String(64), nullable=True),
    Column("stage", String(24), nullable=False, default="queued", index=True),
    Column("claim_count", Integer, nullable=False, server_default="0", default=0),
    Column("payload", JSON(none_as_null=True), nullable=False),
    Column("checkpoint", JSON(none_as_null=True), nullable=True),
    Column("winner_run_id", Integer, ForeignKey("runs.id"), nullable=True),
    # Equals base_run_id while this order is the sole claimant / winner. It is
    # NULL after rejection so a corrected order can take the same draft. The
    # unique index is the final concurrency guard after the row lock check.
    Column("draft_claim_id", Integer, nullable=True),
    Column("created_at", BigInteger, nullable=False),
    Column("updated_at", BigInteger, nullable=False),
    UniqueConstraint("actor", "idempotency_key", name="uq_continuation_actor_key"),
    UniqueConstraint("draft_claim_id", name="uq_continuation_draft_claim"),
)
