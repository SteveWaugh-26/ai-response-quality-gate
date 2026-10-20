
from fastapi import APIRouter, HTTPException, Query

from app.db.database import list_failures

router = APIRouter(prefix="/api", tags=["Failures"])


@router.get("/failures")
def get_failures(
    limit: int = Query(default=100, ge=1, le=500),
):
    """Return recent executions that ended with unresolved failures."""

    try:
        failures = list_failures(limit=limit)

        return {
            "total": len(failures),
            "failures": failures,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not retrieve execution failures: {str(exc)}",
        ) from exc
