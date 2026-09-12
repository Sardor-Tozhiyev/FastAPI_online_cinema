from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.accounts.bootstrap import seed_user_groups
from src.accounts.routers import router as accounts_router
from src.cart.routers import router as cart_router
from src.config import settings
from src.database import AsyncSessionLocal, Base, engine
from src.movies.routers import router as movies_router
from src.orders.routers import router as orders_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # In production, schema is managed by Alembic migrations (see alembic/).
    # create_all here is a convenience for local/dev boot and is a no-op once
    # migrations have already created the tables.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as session:
        await seed_user_groups(session)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="API for browsing, purchasing and watching movies online.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(accounts_router)
app.include_router(movies_router)
app.include_router(cart_router)

app.include_router(orders_router)


@app.get("/health", tags=["health"], summary="Liveness probe")
async def health() -> dict:
    return {"status": "ok"}
