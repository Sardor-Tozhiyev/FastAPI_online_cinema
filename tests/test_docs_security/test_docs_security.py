from httpx import AsyncClient

from config import settings


async def test_docs_requires_authentication(client: AsyncClient):
    response = await client.get("/docs")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Basic"


async def test_docs_rejects_wrong_credentials(client: AsyncClient):
    response = await client.get(
        "/docs", auth=(settings.DOCS_USERNAME, "definitely-wrong")
    )
    assert response.status_code == 401


async def test_docs_rejects_wrong_username(client: AsyncClient):
    response = await client.get(
        "/docs", auth=("not-the-admin", settings.DOCS_PASSWORD)
    )
    assert response.status_code == 401


async def test_docs_accessible_with_correct_credentials(client: AsyncClient):
    response = await client.get(
        "/docs", auth=(settings.DOCS_USERNAME, settings.DOCS_PASSWORD)
    )
    assert response.status_code == 200
    assert "swagger-ui" in response.text.lower()


async def test_redoc_requires_authentication(client: AsyncClient):
    response = await client.get("/redoc")
    assert response.status_code == 401


async def test_redoc_accessible_with_correct_credentials(client: AsyncClient):
    response = await client.get(
        "/redoc", auth=(settings.DOCS_USERNAME, settings.DOCS_PASSWORD)
    )
    assert response.status_code == 200


async def test_openapi_json_requires_authentication(client: AsyncClient):
    response = await client.get("/openapi.json")
    assert response.status_code == 401


async def test_openapi_json_accessible_with_correct_credentials(
    client: AsyncClient,
):
    response = await client.get(
        "/openapi.json",
        auth=(settings.DOCS_USERNAME, settings.DOCS_PASSWORD),
    )
    assert response.status_code == 200
    body = response.json()
    assert "paths" in body
    assert "/api/v1/movies" in body["paths"]


async def test_health_endpoint_remains_public(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
