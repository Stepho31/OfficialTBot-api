from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.settings import settings
from app.db import engine
from app.models import Base
from app import stripe_checkout, stripe_webhooks
from app.access import router as access_router
from app.accounts import router as accounts_router
from app.dashboard import router as dashboard_router
from app.proofs import router as proofs_router
from app.broker import me_router as broker_me_router
from app.internal import router as internal_router
from app.api_v1 import router as api_v1_router
from app.health import router as health_router
from app.auth import router as auth_router
from app.user_settings import router as user_settings_router
from app.logging_conf import setup_logging

setup_logging()
app = FastAPI(title="Autopip API")

origins = [settings.FRONTEND_ORIGIN]
if settings.DEV_ALLOW_ALL_CORS:
    origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create tables (dev convenience; in prod use Alembic)
Base.metadata.create_all(bind=engine)

@app.get("/healthz")
def healthz():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"ok": True}

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(stripe_checkout.router)
app.include_router(stripe_webhooks.router)
app.include_router(access_router)
app.include_router(accounts_router)
app.include_router(dashboard_router)
app.include_router(proofs_router)
app.include_router(broker_me_router)
app.include_router(internal_router)
app.include_router(api_v1_router)
app.include_router(user_settings_router)
