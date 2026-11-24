from fastapi import APIRouter, Body, Depends, Header, Response

from src.config.resources import engine
from src.controllers.access import identity, operator
from src.controllers.workbench import new_continuation, retry_continuation
from src.routes.runs import export as export_run
from src.schemas.continuations import ContinuationInput
from src.schemas.runs import RunEntry
from src.constants.job_state import JobState
from src.services import continuations, runs

router = APIRouter(tags=["Continuations"])


def _submit(response, user, form, idempotency_key, x_idempotency_key, *,
            run_id=None, case_id=None, draft_ref=None):
    path_run_id = run_id
    if path_run_id is None and draft_ref is not None:
        path_run_id = continuations.parse_identifier(draft_ref, "底稿编号")
    key = idempotency_key or x_idempotency_key
    entry, replay = new_continuation(
        form or {},
        user,
        path_run_id=path_run_id,
        path_case_id=case_id,
        idempotency_key=key,
        source_case_id=case_id,
        run_case_id=case_id,
    )
    response.status_code = 200 if replay else 202
    return entry


@router.post("/continuations", response_model=RunEntry, status_code=202)
def create_continuation(
    response: Response,
    form: ContinuationInput | None = Body(default=None),
    user=Depends(operator),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
):
    return _submit(response, user, form, idempotency_key, x_idempotency_key)


@router.post("/runs/{run_id}/continuations", response_model=RunEntry, status_code=202)
def continue_run(
    run_id: int,
    response: Response,
    form: ContinuationInput | None = Body(default=None),
    user=Depends(operator),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
):
    return _submit(response, user, form, idempotency_key, x_idempotency_key, run_id=run_id)


@router.post("/runs/{run_id}/continue", response_model=RunEntry, status_code=202)
def continue_run_shortcut(
    run_id: int,
    response: Response,
    form: ContinuationInput | None = Body(default=None),
    user=Depends(operator),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
):
    return _submit(response, user, form, idempotency_key, x_idempotency_key, run_id=run_id)


@router.post("/batches/{run_id}/continuations", response_model=RunEntry, status_code=202)
def continue_batch(
    run_id: int,
    response: Response,
    form: ContinuationInput | None = Body(default=None),
    user=Depends(operator),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
):
    return _submit(response, user, form, idempotency_key, x_idempotency_key, run_id=run_id)


@router.post("/batches/{run_id}/continue", response_model=RunEntry, status_code=202)
def continue_batch_shortcut(
    run_id: int,
    response: Response,
    form: ContinuationInput | None = Body(default=None),
    user=Depends(operator),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
):
    return _submit(response, user, form, idempotency_key, x_idempotency_key, run_id=run_id)


@router.post("/drafts/{draft_ref}/continuations", response_model=RunEntry, status_code=202)
def continue_draft(
    draft_ref: str,
    response: Response,
    form: ContinuationInput | None = Body(default=None),
    user=Depends(operator),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
):
    return _submit(response, user, form, idempotency_key, x_idempotency_key, draft_ref=draft_ref)


@router.post("/drafts/{draft_ref}/continue", response_model=RunEntry, status_code=202)
@router.post("/drafts/{draft_ref}/submit", response_model=RunEntry, status_code=202)
def continue_draft_shortcut(
    draft_ref: str,
    response: Response,
    form: ContinuationInput | None = Body(default=None),
    user=Depends(operator),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
):
    return _submit(response, user, form, idempotency_key, x_idempotency_key, draft_ref=draft_ref)


@router.post("/worksheets/{draft_ref}/continuations", response_model=RunEntry, status_code=202)
def continue_worksheet(
    draft_ref: str,
    response: Response,
    form: ContinuationInput | None = Body(default=None),
    user=Depends(operator),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
):
    return _submit(response, user, form, idempotency_key, x_idempotency_key, draft_ref=draft_ref)


@router.post("/cases/{case_id}/continuations", response_model=RunEntry, status_code=202)
@router.post("/cases/{case_id}/continue", response_model=RunEntry, status_code=202)
def continue_case(
    case_id: int,
    response: Response,
    form: ContinuationInput | None = Body(default=None),
    user=Depends(operator),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
):
    return _submit(response, user, form, idempotency_key, x_idempotency_key, case_id=case_id)


@router.get("/continuations/{run_id}", response_model=RunEntry, dependencies=[Depends(identity)])
def continuation_detail(run_id: int):
    with engine.connect() as db:
        return runs.get(db, run_id)


@router.post("/continuations/{run_id}/retry", response_model=RunEntry, status_code=202)
def retry_continuation_job(run_id: int, user=Depends(operator)):
    return retry_continuation(run_id, user)


@router.post("/runs/{run_id}/retry", response_model=RunEntry, status_code=202)
def retry_run_continuation(run_id: int, user=Depends(operator)):
    return retry_continuation(run_id, user)


@router.post("/batches/{run_id}/retry", response_model=RunEntry, status_code=202)
def retry_batch_continuation(run_id: int, user=Depends(operator)):
    return retry_continuation(run_id, user)


@router.get("/batches/{run_id}", response_model=RunEntry, dependencies=[Depends(identity)])
def batch_detail(run_id: int):
    with engine.connect() as db:
        return runs.get(db, run_id)


@router.get("/drafts", response_model=list[RunEntry], dependencies=[Depends(identity)])
def list_drafts():
    with engine.connect() as db:
        return [entry for entry in runs.list_entries(db) if entry["status"] == JobState.DONE]


@router.get("/drafts/{draft_ref}", response_model=RunEntry, dependencies=[Depends(identity)])
def draft_detail(draft_ref: str):
    run_id = continuations.parse_identifier(draft_ref, "底稿编号")
    with engine.connect() as db:
        return runs.get(db, run_id)


@router.get("/continuations/{run_id}/export", dependencies=[Depends(identity)])
def continuation_export(run_id: int):
    return export_run(run_id)


@router.get("/continuations/{run_id}/credential", dependencies=[Depends(identity)])
def continuation_credential(run_id: int):
    return export_run(run_id)


@router.get("/runs/{run_id}/credential", dependencies=[Depends(identity)])
def run_credential(run_id: int):
    return export_run(run_id)
