"""FastAPI application factory with CORS restricted to localhost:3000."""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routers import health, subscriptions, scan, accounts
from backend.api.routers import scan_async
from backend.api.routers import payment_events

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: mark any in-flight scan jobs as interrupted (server-restart recovery)."""
    db_path = os.getenv("DB_PATH", "data/subscriptions.db")
    if Path(db_path).exists():
        try:
            scan_async.mark_interrupted_jobs(db_path)
        except Exception as exc:
            # Non-fatal: if the scan_jobs table doesn't exist yet, log and continue
            logger.debug("Startup interrupt-recovery skipped: %s", exc)
    yield


app = FastAPI(
    title="Subscription Tracker API",
    version="0.2.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js dev server only — never "*"
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)

app.include_router(health.router)
app.include_router(subscriptions.router)
app.include_router(scan.router)
app.include_router(scan_async.router)
app.include_router(accounts.router)
app.include_router(payment_events.router)
