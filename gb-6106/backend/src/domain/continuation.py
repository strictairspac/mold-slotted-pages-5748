"""Strict night-shift continuation replay on a persisted day-shift draft page.

A continuation is all-or-nothing: operations are replayed on a private copy /
resumable checkpoint. The published draft snapshot is replaced only after every
operation has succeeded and the database transaction commits.
"""
from dataclasses import dataclass
from typing import Any

from .page import HEADER_BYTES, SlottedPage
from .scenario import apply_operation, build_result, validate


class ContinuationError(ValueError):
    """The whole continuation order must be returned to the operator."""

    def __init__(self, message, *, step=None, key=None):
        super().__init__(message)
        self.step = step
        self.key = key


class DraftConflictError(ContinuationError):
    def __init__(self, message, *, winner_run_id, **extra):
        super().__init__(message)
        self.winner_run_id = winner_run_id
        self.details = {"winner_run_id": winner_run_id, **extra}


@dataclass
class ContinuationSession:
    page: SlottedPage
    operations: list[dict[str, Any]]
    next_step: int = 0
    rows: list[dict[str, Any]] | None = None
    compactions: int = 0
    peak_waste: int = 0

    def __post_init__(self):
        if self.rows is None:
            self.rows = []

    @classmethod
    def start(cls, base_snapshot: dict, operations: list[dict], capacity: int | None = None):
        validate({"operations": operations})
        page = SlottedPage.from_snapshot(base_snapshot)
        if capacity is not None and int(capacity) != page.size:
            raise ContinuationError("续单必须沿用底稿页容量，不能改用其他模拟页容量")
        if page.size < HEADER_BYTES:
            raise ContinuationError(f"至少需要 {HEADER_BYTES} 字节页头")
        return cls(page=page, operations=operations)

    @classmethod
    def restore(cls, checkpoint: dict, operations: list[dict]):
        if not isinstance(checkpoint, dict):
            raise ContinuationError("续单中断点格式不正确")
        session = cls(
            page=SlottedPage.from_snapshot(checkpoint["page"]),
            operations=operations,
            next_step=int(checkpoint.get("next_step", 0)),
            rows=list(checkpoint.get("rows", [])),
            compactions=int(checkpoint.get("compactions", 0)),
            peak_waste=int(checkpoint.get("peak_waste", 0)),
        )
        if not 0 <= session.next_step <= len(operations):
            raise ContinuationError("续单中断点超出操作范围")
        return session

    def checkpoint(self):
        return {
            "version": 1,
            "next_step": self.next_step,
            "page": self.page.snapshot(),
            "rows": self.rows,
            "compactions": self.compactions,
            "peak_waste": self.peak_waste,
        }

    def step(self):
        if self.next_step >= len(self.operations):
            return False
        step_number = self.next_step + 1
        operation = self.operations[self.next_step]
        try:
            row = apply_operation(self.page, operation, step_number)
        except ContinuationError:
            raise
        except ValueError as exc:
            key = operation.get("key") if isinstance(operation, dict) else None
            raise ContinuationError(f"第 {step_number} 笔装不下，整单退回：{exc}",
                                    step=step_number, key=key) from exc
        if operation.get("op") == "compact" or row.get("结果") == "压实后落盘":
            self.compactions += 1
        self.peak_waste = max(self.peak_waste, self.page.fragmented)
        self.rows.append(row)
        self.next_step += 1
        return True

    def run_all(self):
        while self.step():
            pass
        return self

    @property
    def complete(self):
        return self.next_step == len(self.operations)

    def result(self, base_run_id=None):
        if not self.complete:
            raise ContinuationError("续单尚未全部写成，不能开放新凭据")
        output = build_result(
            self.page,
            self.rows,
            denied=0,
            compactions=self.compactions,
            peak_waste=self.peak_waste,
        )
        output["summary"] = (
            f"夜班续单整单写成：{output['summary'].split('：', 1)[-1]}"
        )
        output["continuation"] = {
            "all_or_nothing": True,
            "base_run_id": base_run_id,
            "capacity": self.page.size,
            "slots_reused": False,
            "tombstoned_slots_reassigned": False,
        }
        return output

    def final_snapshot(self):
        if not self.complete:
            raise ContinuationError("续单尚未全部写成，不能发布底稿快照")
        return self.page.snapshot()


def plan_continuation(base_snapshot, operations, capacity=None, base_run_id=None):
    """Dry-run an entire order without publishing it."""
    session = ContinuationSession.start(base_snapshot, operations, capacity)
    session.run_all()
    return {
        "result": session.result(base_run_id),
        "snapshot": session.final_snapshot(),
        "checkpoint": session.checkpoint(),
    }


# Concise aliases for callers/tests that name the use case differently.
apply_continuation = plan_continuation
commit_continuation = plan_continuation
continue_order = plan_continuation
process_continuation = plan_continuation
