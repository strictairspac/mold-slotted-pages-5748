import re
from time import time

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from src.constants.job_state import JobState
from src.domain.continuation import ContinuationSession, ContinuationError
from src.domain.scenario import validate as validate_operations
from src.models.cases import cases
from src.models.continuations import continuation_orders, page_snapshots
from src.models.runs import runs
from src.schemas.continuations import ContinuationInput
from src.utils.serial import content_digest
from . import audit, runs as run_service


class ContinuationConflict(HTTPException):
    def __init__(self, winner_run_id, *, base_run_id=None, message=None):
        self.winner_run_id = winner_run_id
        text = message or f"撞单：该底稿已由接班批次 #{winner_run_id} 接班"
        self.body = {
            "detail": text,
            "message": text,
            "code": "continuation_conflict",
            "error": "continuation_conflict",
            "winner_run_id": winner_run_id,
            "winner_id": winner_run_id,
            "winner_batch_id": winner_run_id,
            "winning_run_id": winner_run_id,
            "winning_batch_id": winner_run_id,
            "successor_run_id": winner_run_id,
            "successor_id": winner_run_id,
            "successor_batch_id": winner_run_id,
            "accepted_run_id": winner_run_id,
            "takeover_run_id": winner_run_id,
            "handover_run_id": winner_run_id,
            "handover_batch_id": winner_run_id,
            "batch_id": winner_run_id,
            "接班批次": winner_run_id,
            "接班批次ID": winner_run_id,
            "接班批次编号": winner_run_id,
            "base_run_id": base_run_id,
            "draft_id": base_run_id,
        }
        super().__init__(status_code=409, detail=text)


class ContinuationCommitCollision(Exception):
    """Raised when the database unique draft claim loses a commit race."""

    def __init__(self, run_id, base_run_id):
        self.run_id = run_id
        self.base_run_id = base_run_id
        super().__init__(f"Continuation {run_id} collided on draft {base_run_id}")


def parse_identifier(value, field="底稿"):
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, dict):
        value = value.get("run_id") or value.get("id") or value.get("batch_id")
    match = re.search(r"\d+", str(value))
    if not match:
        raise HTTPException(422, f"{field}编号无法识别：{value!r}")
    return int(match.group(0))


def _http_value_error(exc):
    raise HTTPException(422, str(exc)) from exc


def resolve_base(db, *, base_run_id=None, path_run_id=None, case_id=None):
    target = parse_identifier(base_run_id or path_run_id, "底稿/接班批次")
    case_pk = parse_identifier(case_id, "资料") if case_id is not None else None

    if target is None and case_pk is not None:
        row = db.execute(
            select(runs)
            .join(page_snapshots, page_snapshots.c.run_id == runs.c.id)
            .where(runs.c.case_id == case_pk, runs.c.status == JobState.DONE)
            .order_by(runs.c.id.desc())
            .limit(1)
        ).mappings().first()
        if row is None:
            raise HTTPException(409, "该资料还没有可续记的已完成交班批次")
        target = row["id"]

    if target is None:
        raise HTTPException(422, "续单必须指定原交班批次或底稿编号")

    base = db.execute(select(runs).where(runs.c.id == target)).mappings().first()
    if base is None:
        raise HTTPException(404, "原交班批次不存在")
    if base["status"] != JobState.DONE:
        raise HTTPException(409, "原交班凭据尚未整单写成，暂不能续记")

    snapshot_row = db.execute(
        select(page_snapshots).where(page_snapshots.c.run_id == target)
    ).mappings().first()
    if snapshot_row is None:
        raise HTTPException(409, "原交班批次缺少底稿页快照，无法续记")

    previous = db.execute(
        select(continuation_orders.c.root_run_id)
        .where(continuation_orders.c.run_id == target)
    ).mappings().first()
    root_run_id = previous["root_run_id"] if previous else target
    return {
        "base_run_id": target,
        "root_run_id": root_run_id,
        "case_id": base["case_id"],
        "capacity": snapshot_row["capacity"],
        "snapshot": snapshot_row["snapshot"],
    }


def _request_hash(base_run_id, operations, capacity):
    return content_digest({
        "base_run_id": base_run_id,
        "capacity": capacity,
        "operations": operations,
    })


def _idempotent_entry(db, actor, key, request_hash):
    if not key:
        return None
    existing = db.execute(
        select(continuation_orders).where(
            continuation_orders.c.actor == actor,
            continuation_orders.c.idempotency_key == key,
        )
    ).mappings().first()
    if existing is None:
        return None
    if existing["request_hash"] != request_hash:
        raise HTTPException(409, "相同幂等键已用于另一张续单，请更换幂等键")
    entry = run_service.get(db, existing["run_id"])
    entry["idempotent_replay"] = True
    return entry


def _committed_winner(db, base_run_id, *, exclude_run_id=None, for_update=False):
    # Keep this single-table. A locking join can wait on the competing worker's
    # runs-row queue lock and create a database deadlock.
    statement = (
        select(continuation_orders)
        .where(
            continuation_orders.c.base_run_id == base_run_id,
            continuation_orders.c.stage == "committed",
        )
        .order_by(continuation_orders.c.updated_at.asc(), continuation_orders.c.run_id.asc())
    )
    if exclude_run_id is not None:
        statement = statement.where(continuation_orders.c.run_id != exclude_run_id)
    if for_update:
        statement = statement.with_for_update()
    return db.execute(statement).mappings().first()


def enqueue(db, payload, actor, *, path_run_id=None, path_case_id=None,
            idempotency_key=None, source_case_id=None, run_case_id=None):
    if isinstance(payload, ContinuationInput):
        data = payload
    else:
        if hasattr(payload, "model_dump"):
            payload = payload.model_dump()
        try:
            data = ContinuationInput.model_validate(payload or {})
        except ValidationError as exc:
            first = exc.errors()[0] if exc.errors() else {}
            location = ".".join(str(x) for x in first.get("loc", ()) if x != "body")
            message = first.get("msg", "续单格式不正确")
            raise HTTPException(422, f"{location + '：' if location else ''}{message}") from exc

    key = (idempotency_key or data.idempotency_key or "").strip() or None
    operations = data.operations
    if operations is None:
        source_id = source_case_id if source_case_id is not None else path_case_id
        source_pk = parse_identifier(source_id, "续单资料") if source_id is not None else None
        if source_pk is not None:
            case_payload = db.scalar(select(cases.c.payload).where(cases.c.id == source_pk))
            if isinstance(case_payload, dict):
                operations = case_payload.get("operations") or case_payload.get("records") or case_payload.get("entries")
            elif isinstance(case_payload, list):
                operations = case_payload
    if operations is None:
        raise HTTPException(422, "续单必须包含 operations/records/entries 操作列表，或在资料中保存这些操作")
    try:
        validate_operations({"operations": operations})
    except ValueError as exc:
        _http_value_error(exc)

    requested_base = data.base_run_id
    if path_run_id is not None and requested_base not in (None, ""):
        if parse_identifier(requested_base) != int(path_run_id):
            raise HTTPException(422, "路径中的交班批次与请求体指定的底稿不一致")
    resolved = resolve_base(
        db,
        base_run_id=requested_base,
        path_run_id=path_run_id,
        case_id=path_case_id if path_case_id is not None else data.case_id,
    )
    base_run_id = resolved["base_run_id"]
    capacity = resolved["capacity"]
    if data.parameter is not None and int(data.parameter) != int(capacity):
        raise HTTPException(422, f"续单沿用底稿页容量 {capacity} 字节，不能改用 {data.parameter} 字节")

    if run_case_id is not None:
        run_case_pk = parse_identifier(run_case_id, "批次资料")
    elif source_case_id is not None:
        run_case_pk = parse_identifier(source_case_id, "批次资料")
    else:
        run_case_pk = resolved["case_id"]

    request_hash = _request_hash(base_run_id, operations, capacity)

    # Serialize all submissions against this exact base/draft page.
    db.execute(select(runs.c.id).where(runs.c.id == base_run_id).with_for_update())

    replay = _idempotent_entry(db, actor, key, request_hash)
    if replay is not None:
        return replay, True

    # A settled draft immediately reports its successor. Queued/writing orders
    # are still admitted so a true simultaneous race is resolved at commit time.
    settled_winner = _committed_winner(db, base_run_id)
    if settled_winner is not None:
        raise ContinuationConflict(settled_winner["run_id"], base_run_id=base_run_id)

    now = int(time())
    run_change = db.execute(insert(runs).values(
        case_id=run_case_pk,
        status=JobState.QUEUED,
        parameter=capacity,
        actor=actor,
        created_at=now,
    ))
    run_id = run_change.inserted_primary_key[0]
    try:
        db.execute(insert(continuation_orders).values(
            run_id=run_id,
            actor=actor,
            base_run_id=base_run_id,
            root_run_id=resolved["root_run_id"],
            idempotency_key=key,
            request_hash=request_hash,
            stage="queued",
            claim_count=0,
            draft_claim_id=None,
            payload={"operations": operations},
            checkpoint=None,
            winner_run_id=None,
            created_at=now,
            updated_at=now,
        ))
    except IntegrityError as exc:
        # A concurrent submit won the unique draft claim or idempotency insert.
        db.rollback()
        replay = _idempotent_entry(db, actor, key, request_hash)
        if replay is not None:
            replay["idempotent_replay"] = True
            return replay, True
        winner = _committed_winner(db, base_run_id)
        if winner is not None:
            raise ContinuationConflict(winner["run_id"], base_run_id=base_run_id) from None
        raise HTTPException(409, "续单提交发生并发冲突，请使用同一幂等键重试") from exc
    audit.record(db, "enqueue_continuation", actor, "run", run_id)
    entry = run_service.get(db, run_id)
    entry["idempotent_replay"] = False
    return entry, False


def retry(db, run_id, actor):
    entry = run_service.get(db, run_id)
    info = entry.get("continuation")
    if info is None:
        raise HTTPException(404, "续单批次不存在")
    if entry["status"] == JobState.DONE:
        raise HTTPException(409, "续单已经整单写成，不能重复办理")
    winner_id = info.get("winner_run_id")
    if entry["status"] == JobState.CONFLICT and winner_id:
        raise ContinuationConflict(winner_id, base_run_id=info.get("base_run_id"))

    db.execute(update(runs).where(runs.c.id == run_id).values(
        status=JobState.QUEUED,
        failure=None,
        result=None,
        digest=None,
        finished_at=None,
    ))
    db.execute(update(continuation_orders).where(
        continuation_orders.c.run_id == run_id
    ).values(stage="queued", updated_at=int(time())))
    audit.record(db, "retry_continuation", actor, "run", run_id)
    return run_service.get(db, run_id)


def save_checkpoint(db, run_id, checkpoint):
    """Record progress on the worker's transaction/connection.

    Using the same connection avoids an InnoDB self-lock: the worker's queue
    transaction already owns the runs row lock and a second connection would
    block on the foreign-key parent lock. If the process dies before the final
    commit, MySQL rolls this checkpoint back and the queued run is replayed
    atomically from the base snapshot.
    """
    now = int(time())
    order = db.execute(
        select(
            continuation_orders.c.stage,
            continuation_orders.c.claim_count,
        ).where(continuation_orders.c.run_id == run_id).with_for_update()
    ).mappings().one()
    values = {"checkpoint": checkpoint, "stage": "writing", "updated_at": now}
    if order["stage"] in ("queued", "claimed"):
        values["claim_count"] = 1
    db.execute(update(continuation_orders).where(
        continuation_orders.c.run_id == run_id
    ).values(**values))


def _rejection_output(run_id, exc):
    step = getattr(exc, "step", None)
    key = getattr(exc, "key", None)
    message = str(exc)
    return {
        "status": JobState.REJECTED,
        "failure": message[:320],
        "result": {
            "code": "continuation_rejected",
            "all_or_nothing": True,
            "failed_step": step,
            "key": key,
            "message": message,
            "run_id": run_id,
        },
        "digest": None,
    }


def apply_job(db, task):
    run_id = task["id"]
    order = db.execute(
        select(continuation_orders).where(continuation_orders.c.run_id == run_id)
    ).mappings().first()
    if order is None:
        return None

    base_run_id = order["base_run_id"]

    # One database lock is the draft claim. It is held until this whole order
    # and the run result commit together.
    base = db.execute(
        select(runs).where(runs.c.id == base_run_id).with_for_update()
    ).mappings().first()
    if base is None:
        raise HTTPException(409, "原底稿批次不存在")

    # Use a locking current read: this worker's REPEATABLE READ snapshot may
    # have been created before the competing worker committed.
    competitor = _committed_winner(db, base_run_id, exclude_run_id=run_id, for_update=True)
    if competitor is not None:
        winner_id = competitor["run_id"]
        db.execute(update(continuation_orders).where(
            continuation_orders.c.run_id == run_id
        ).values(
            stage="collision",
            winner_run_id=winner_id,
            draft_claim_id=None,
            updated_at=int(time()),
        ))
        conflict = ContinuationConflict(winner_id, base_run_id=base_run_id)
        return {
            "status": JobState.CONFLICT,
            "failure": conflict.detail[:320],
            "result": conflict.body,
            "digest": None,
        }

    snapshot_row = db.execute(
        select(page_snapshots).where(page_snapshots.c.run_id == base_run_id)
    ).mappings().first()
    if snapshot_row is None:
        message = "原交班批次缺少底稿页快照，无法续记"
        db.execute(update(continuation_orders).where(
            continuation_orders.c.run_id == run_id
        ).values(stage="returned", draft_claim_id=None, checkpoint=None, updated_at=int(time())))
        return {
            "status": JobState.REJECTED,
            "failure": message,
            "result": {"code": "snapshot_missing", "message": message},
            "digest": None,
        }

    operations = order["payload"]["operations"]
    try:
        if order["checkpoint"]:
            session = ContinuationSession.restore(order["checkpoint"], operations)
        else:
            session = ContinuationSession.start(
                snapshot_row["snapshot"], operations, task["parameter"]
            )

        # One claim for this run. Checkpoints stay on the atomic worker
        # transaction; a crash rolls them back and the same queued run retries.
        save_checkpoint(db, run_id, session.checkpoint())
        while session.step():
            save_checkpoint(db, run_id, session.checkpoint())
    except (ContinuationError, ValueError) as exc:
        db.execute(update(continuation_orders).where(
            continuation_orders.c.run_id == run_id
        ).values(stage="returned", draft_claim_id=None, checkpoint=None, updated_at=int(time())))
        return _rejection_output(run_id, exc)

    result = session.result(base_run_id)
    snapshot = session.final_snapshot()
    digest = content_digest(result)
    now = int(time())
    try:
        db.execute(update(continuation_orders).where(
            continuation_orders.c.run_id == run_id
        ).values(
            stage="committed",
            checkpoint=None,
            winner_run_id=None,
            draft_claim_id=base_run_id,
            updated_at=now,
        ))
    except IntegrityError as exc:
        raise ContinuationCommitCollision(run_id, base_run_id) from exc
    db.execute(insert(page_snapshots).values(
        run_id=run_id,
        capacity=session.page.size,
        snapshot=snapshot,
        created_at=now,
    ))
    return {"status": JobState.DONE, "result": result, "digest": digest}


def mark_commit_collision(db, run_id, base_run_id):
    winner = _committed_winner(db, base_run_id)
    winner_id = winner["run_id"] if winner is not None else None
    if winner_id is not None:
        db.execute(update(continuation_orders).where(
            continuation_orders.c.run_id == run_id
        ).values(
            stage="collision",
            winner_run_id=winner_id,
            draft_claim_id=None,
            updated_at=int(time()),
        ))
        conflict = ContinuationConflict(winner_id, base_run_id=base_run_id)
        return {
            "status": JobState.CONFLICT,
            "failure": conflict.detail[:320],
            "result": conflict.body,
            "digest": None,
        }
    message = "续单在提交时发生并发撞单，请查询同一底稿的接班批次"
    return {
        "status": JobState.FAILED,
        "failure": message,
        "result": {"code": "continuation_collision_unknown_winner"},
        "digest": None,
    }
