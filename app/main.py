from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
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
import logging

setup_logging()
app = FastAPI(title="Autopip API")

# Configure CORS with comprehensive origin matching
cors_origins = [
    "https://official-t-bot-ui.vercel.app",
    "https://official-t-bot.vercel.app",
    "https://official-t-bot-1ddkcd33f-stepho31s-projects.vercel.app",
    "https://official-t-bot-ui-git-main-stepho31s-projects.vercel.app",
    "http://localhost:3000",
    "http://localhost:3001",
]

# Add regex pattern to match all Vercel preview deployments
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Helper function to check if origin is allowed
def _is_origin_allowed(origin: str) -> bool:
    """Check if the origin is allowed for CORS."""
    if not origin:
        return False
    if origin in cors_origins:
        return True
    import re
    if re.match(r"https://.*\.vercel\.app", origin):
        return True
    return False

# Helper function to add CORS headers to response
def _add_cors_headers(response: JSONResponse, origin: str) -> JSONResponse:
    """Add CORS headers to a response if origin is allowed."""
    if _is_origin_allowed(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
    return response

# Exception handler for HTTP exceptions to ensure CORS headers are set
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions with CORS headers."""
    origin = request.headers.get("origin", "")
    response = JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )
    return _add_cors_headers(response, origin)

# Exception handler for validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with CORS headers."""
    origin = request.headers.get("origin", "")
    response = JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
    )
    return _add_cors_headers(response, origin)

# Global exception handler for unhandled exceptions
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler that ensures CORS headers are set on all errors."""
    logger = logging.getLogger(__name__)
    
    # Log the error for debugging
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    origin = request.headers.get("origin", "")
    response = JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )
    return _add_cors_headers(response, origin)


# Create tables (dev convenience; in prod use Alembic)
Base.metadata.create_all(bind=engine)

@app.get("/healthz")
def healthz():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"ok": True}

@app.get("/favicon.ico")
async def favicon():
    """Handle favicon requests to prevent 404 errors."""
    from fastapi.responses import Response
    return Response(status_code=204)

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
