from fastapi import APIRouter, Depends, Response

from src.config.resources import engine
from src.controllers.access import identity, operator
from src.controllers.workbench import new_case, new_continuation, new_run
from src.schemas.cases import CaseEntry, CaseInput
from src.schemas.continuations import ContinuationInput
from src.schemas.runs import RunEntry, RunInput
from src.services import cases

router = APIRouter(prefix="/cases", tags=["Cases"])


@router.get("", response_model=list[CaseEntry], dependencies=[Depends(identity)])
def list_cases():
    with engine.connect() as db:
        return cases.list_entries(db)


@router.get("/{case_id}", response_model=CaseEntry, dependencies=[Depends(identity)])
def case_detail(case_id: int):
    with engine.connect() as db:
        return cases.get(db, case_id)


@router.post("", response_model=CaseEntry, status_code=201)
def register(form: CaseInput, user=Depends(operator)):
    return new_case(form, user)


@router.post("/{case_id}/runs", response_model=RunEntry, status_code=202)
def schedule(case_id: int, form: RunInput, response: Response, user=Depends(operator)):
    continuation_payload = ContinuationInput.model_validate(form.model_dump())
    extra = form.model_extra or {}
    mode = str(extra.get("mode") or extra.get("type") or "").lower()
    is_continuation = (
        continuation_payload.base_run_id not in (None, "")
        or bool(form.continuation)
        or continuation_payload.operations is not None
        or mode in {"continuation", "continue", "night", "night_shift"}
    )
    if is_continuation:
        entry, replay = new_continuation(
            continuation_payload,
            user,
            path_run_id=continuation_payload.base_run_id,
            path_case_id=case_id,
            idempotency_key=form.idempotency_key,
            source_case_id=case_id,
            run_case_id=case_id,
        )
        response.status_code = 200 if replay else 202
        return entry
    return new_run(case_id, form, user)
