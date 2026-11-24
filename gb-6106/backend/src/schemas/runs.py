from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from src.constants.job_state import JobState


class RunInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    parameter: int | None = Field(default=None, strict=True, ge=1)
    base_run_id: Any = None
    base_batch_id: Any = None
    draft_id: Any = None
    continuation: bool | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)
    operations: list[dict] | None = None

    @model_validator(mode="after")
    def require_parameter_for_normal_run(self):
        extra = self.model_extra or {}
        aliases = (
            self.base_run_id, self.base_batch_id, self.draft_id,
            extra.get("source_run_id"), extra.get("parent_run_id"),
            extra.get("handover_run_id"), extra.get("base"), extra.get("draft"),
        )
        mode = str(extra.get("mode") or extra.get("type") or "").lower()
        has_base = any(value not in (None, "") for value in aliases)
        is_continuation = has_base or bool(self.continuation) or self.operations is not None or mode in {
            "continuation", "continue", "night", "night_shift"
        }
        if self.parameter is None and not is_continuation:
            raise ValueError("普通执行批次必须提供 parameter；续单可沿用底稿页容量")
        return self


class RunEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    case_id: int
    case_title: str | None = None
    status: JobState
    parameter: int
    actor: str
    created_at: int
    finished_at: int | None
    result: dict | None
    failure: str | None
    digest: str | None
    continuation: dict | None = None
    base_run_id: int | None = None
    root_run_id: int | None = None
    winner_run_id: int | None = None
    winner_id: int | None = None
    winner_batch_id: int | None = None
    successor_run_id: int | None = None
    successor_id: int | None = None
    successor_batch_id: int | None = None
    idempotency_key: str | None = None
    idempotent_replay: bool | None = None
