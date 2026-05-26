"""FastAPI application factory with CORS restricted to localhost:3000."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routers import health, subscriptions, scan

app = FastAPI(
    title="Subscription Tracker API",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js dev server only — never "*"
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(health.router)
app.include_router(subscriptions.router)
app.include_router(scan.router)
