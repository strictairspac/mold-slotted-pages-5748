import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from scripts.seed_demo import seed, setup_schema
from src.config.settings import SEED_DEMO
from src.domain.scenario import CONFIG
from src.middlewares.errors import catch_errors
from src.middlewares.request_id import request_id
from src.routes import cases, continuations, runs, session, system
from src.services.continuations import ContinuationConflict


@asynccontextmanager
async def lifespan(_app):
    setup_schema()
    if SEED_DEMO:
        try:
            seed()
        except Exception:
            logging.getLogger(__name__).exception("Demo seed failed")
    yield


app = FastAPI(title=CONFIG["title"], lifespan=lifespan)
app.middleware("http")(catch_errors)
app.middleware("http")(request_id)


@app.exception_handler(ContinuationConflict)
async def continuation_conflict_handler(_request: Request, exc: ContinuationConflict):
    return JSONResponse(status_code=exc.status_code, content=exc.body, headers=exc.headers)


for group in (system, session, cases, runs, continuations):
    app.include_router(group.router)
