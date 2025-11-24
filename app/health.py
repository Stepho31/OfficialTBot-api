from fastapi import APIRouter

from sqlalchemy import text

from app.db import async_session_factory


router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    db_status = "unknown"
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"

    return {
        "status": "ok",
        "db": db_status,
    }

