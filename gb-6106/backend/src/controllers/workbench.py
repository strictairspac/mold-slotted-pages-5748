from redis.exceptions import RedisError
from src.config.resources import cache, engine
from src.services import cases, continuations, runs, reviews


def _wake_worker(run_id):
    try:
        cache.lpush("workbench:wake", str(run_id))
        cache.ltrim("workbench:wake", 0, 99)
    except RedisError:
        # The database holds the durable queue. The worker also polls it.
        pass


def new_case(data, user):
    with engine.begin() as db:
        return cases.create(db, data, user["username"])


def new_run(case_id, data, user):
    with engine.begin() as db:
        run = runs.enqueue(db, case_id, data.parameter, user["username"])
    _wake_worker(run["id"])
    return run


def new_continuation(data, user, *, path_run_id=None, path_case_id=None,
                     idempotency_key=None, source_case_id=None, run_case_id=None):
    with engine.begin() as db:
        entry, replay = continuations.enqueue(
            db,
            data,
            user["username"],
            path_run_id=path_run_id,
            path_case_id=path_case_id,
            idempotency_key=idempotency_key,
            source_case_id=source_case_id,
            run_case_id=run_case_id,
        )
        run_id = entry["id"]
    if not replay:
        _wake_worker(run_id)
    return entry, replay


def retry_continuation(run_id, user):
    with engine.begin() as db:
        entry = continuations.retry(db, run_id, user["username"])
    _wake_worker(run_id)
    return entry


def new_review(run_id, data, user):
    with engine.begin() as db:
        return reviews.sign(db, run_id, data, user["username"])
