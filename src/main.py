from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi

from accounts.bootstrap import seed_user_groups
from accounts.routers import router as accounts_router
from cart.routers import router as cart_router
from config import settings
from database import AsyncSessionLocal, Base, engine
from docs_security import require_docs_access
from movies.routers import router as movies_router
from orders.routers import router as orders_router
from payments.routers import router as payments_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # In production, schema is managed by Alembic migrations (see alembic/).
    # create_all here is a convenience for local/dev boot and is a no-op once
    # migrations have already created the tables.
    async with AsyncSessionLocal() as session:
        await seed_user_groups(session)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="API for browsing, purchasing and watching movies online.",
    version="0.1.0",
    lifespan=lifespan,
    # The default /docs, /redoc, /openapi.json are disabled here and
    # re-declared below behind HTTP Basic Auth (see src/docs_security.py),
    # so API documentation isn't publicly browsable.
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.include_router(accounts_router)
app.include_router(movies_router)
app.include_router(cart_router)
app.include_router(orders_router)
app.include_router(payments_router)


@app.get("/health", tags=["health"], summary="Liveness probe")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/openapi.json", include_in_schema=False)
async def openapi_json(_: str = Depends(require_docs_access)) -> dict:
    return get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )


@app.get("/docs", include_in_schema=False)
async def swagger_docs(_: str = Depends(require_docs_access)):
    return get_swagger_ui_html(
        openapi_url="/openapi.json", title=f"{app.title} — Swagger UI"
    )


@app.get("/redoc", include_in_schema=False)
async def redoc_docs(_: str = Depends(require_docs_access)):
    return get_redoc_html(
        openapi_url="/openapi.json", title=f"{app.title} — ReDoc"
    )
