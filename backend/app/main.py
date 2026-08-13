from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api.approvals import router as approvals_router
from app.api.decision_package import router as decision_package_router
from app.api.execution_tracking import router as execution_tracking_router
from app.api.impact_dag import router as impact_dag_router
from app.api.incidents import router as incidents_router
from app.api.post_report import router as post_report_router
from app.api.simulate import router as simulate_router
from app.api.snapshots import router as snapshots_router
from app.api.sop_dispatch import router as sop_dispatch_router
from app.api.stream import router as stream_router
from app.core.config import settings
from app.db import check_db_connection

app = FastAPI(
    title="Moveai Supply Chain Decision Platform",
    version="0.1.0",
    description=(
        "platform-infra baseline: DB schema, seed scenarios, and local "
        "runtime that every other workflow module builds on."
    ),
)

# CORS for the frontend dev server. allow_origins takes a list because
# FRONTEND_ORIGIN can name more than one allowed origin (comma-separated --
# see Settings.frontend_origins) -- "localhost" and "127.0.0.1" are distinct
# origins to a browser even on the same machine/port, and a real CORS error
# (frontend reachable at 127.0.0.1:5173) was traced to only localhost:5173
# being allowed here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(incidents_router)
app.include_router(snapshots_router)
app.include_router(impact_dag_router)
app.include_router(simulate_router)
app.include_router(decision_package_router)
app.include_router(approvals_router)
app.include_router(sop_dispatch_router)
app.include_router(execution_tracking_router)
app.include_router(stream_router)
app.include_router(post_report_router)


@app.get("/health")
def health() -> dict:
    """Liveness only — does not touch the database. Use /health/db for
    that."""
    return {"status": "ok", "app_env": settings.app_env}


@app.get("/health/db")
def health_db() -> dict:
    """Readiness — performs an actual round trip to Postgres."""
    if check_db_connection():
        return {"status": "ok", "db": "connected"}
    raise HTTPException(status_code=503, detail="database unavailable")
