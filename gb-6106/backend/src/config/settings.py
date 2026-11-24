import os

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "sqlite:////tmp/gb6106-workbench-default.sqlite3"
)
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
JWT_SECRET = os.environ.get("JWT_SECRET", "local-test-only-jwt-secret")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "Demo-DbWorkbench-2026")
SEED_DEMO = os.environ.get("SEED_DEMO", "true").lower() == "true"
