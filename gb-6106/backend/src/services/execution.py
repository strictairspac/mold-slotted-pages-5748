import logging
from time import time

from sqlalchemy import select, update

from src.config.resources import engine
from src.constants.job_state import JobState
from src.domain import scenario
from src.models.cases import cases
from src.models.continuations import continuation_orders, page_snapshots
from src.models.runs import runs
from src.services import continuations
from src.services.audit import record
from src.utils.serial import content_digest

logger = logging.getLogger(__name__)


def service_one():
    commit_collision = None
    try:
        with engine.begin() as db:
            statement = (
                select(runs).where(runs.c.status == JobState.QUEUED).order_by(runs.c.id)
                .limit(1).with_for_update(skip_locked=True)
            )
            task = db.execute(statement).mappings().first()
            if task is None:
                return False
            try:
                continuation = db.execute(
                    select(continuation_orders.c.run_id).where(
                        continuation_orders.c.run_id == task["id"]
                    )
                ).first()
                if continuation is not None:
                    output = continuations.apply_job(db, task)
                else:
                    payload = db.scalar(select(cases.c.payload).where(cases.c.id == task["case_id"]))
                    result, page = scenario.run_detailed(payload, task["parameter"], db)
                    output = {
                        "status": JobState.DONE,
                        "result": result,
                        "digest": content_digest(result),
                        "snapshot": page.snapshot(),
                    }
            except continuations.ContinuationCommitCollision:
                raise
            except Exception as exc:
                # Let the failed database transaction roll back before persisting the error.
                raise JobFailure(task["id"], exc) from exc
            if output is None:
                raise JobFailure(task["id"], RuntimeError("执行批次缺少可保存的处理结果"))
            snapshot = output.pop("snapshot", None)
            finish(db, task["id"], output, snapshot=snapshot)
            return True
    except continuations.ContinuationCommitCollision as exc:
        commit_collision = exc

    # The unique draft claim lost a cross-database race. Roll back the private
    # write and persist the collision plus the winning batch in a new transaction.
    with engine.begin() as db:
        output = continuations.mark_commit_collision(
            db, commit_collision.run_id, commit_collision.base_run_id
        )
        finish(db, commit_collision.run_id, output)
    return True


class JobFailure(Exception):
    def __init__(self, run_id, cause):
        super().__init__(str(cause))
        self.run_id = run_id
        self.cause = cause


def fail(job_failure):
    with engine.begin() as db:
        run_id = job_failure.run_id
        statement = select(runs.c.status).where(runs.c.id == run_id).with_for_update()
        if db.scalar(statement) != JobState.QUEUED:
            return
        cause = job_failure.cause
        if isinstance(cause, (ValueError, TypeError, KeyError, OverflowError)):
            reason = str(cause) or "输入资料或批次参数不符合要求"
        else:
            reason = "处理失败，请检查 worker 日志"
        finish(db, run_id, {"status": JobState.FAILED, "failure": reason[:320]})


def finish(db, run_id, output, snapshot=None):
    db.execute(update(runs).where(runs.c.id == run_id).values(**output, finished_at=int(time())))
    if snapshot is not None:
        db.execute(page_snapshots.insert().values(
            run_id=run_id,
            capacity=snapshot["size"],
            snapshot=snapshot,
            created_at=int(time()),
        ))
    record(db, str(output["status"]), "worker", "run", run_id)
