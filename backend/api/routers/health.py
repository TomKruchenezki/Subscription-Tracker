import os
from fastapi import APIRouter

router = APIRouter()


@router.get("/api/health")
def health_check():
    mode = "MOCK" if os.getenv("USE_MOCK", "true").lower() not in {"false", "0", "no"} else "GMAIL"
    return {"status": "ok", "mode": mode, "version": "0.1.0"}
