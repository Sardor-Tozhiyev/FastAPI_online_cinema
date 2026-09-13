from httpx import AsyncClient

from config import settings

DOCS_ENDPOINTS = ["/docs", "/redoc", "/openapi.json"]
CONTENT_MARKERS = {
    "/docs": "swagger-ui",
    "/redoc": "redoc",
    "/openapi.json": "paths",
}


async def test_docs_endpoints_require_authentication(client: AsyncClient):
    for path in DOCS_ENDPOINTS:
        response = await client.get(path)
        assert response.status_code == 401, path
        assert response.headers["www-authenticate"] == "Basic"


async def test_docs_rejects_wrong_credentials(client: AsyncClient):
    wrong_password = await client.get(
        "/docs", auth=(settings.DOCS_USERNAME, "definitely-wrong")
    )
    wrong_username = await client.get(
        "/docs", auth=("not-the-admin", settings.DOCS_PASSWORD)
    )
    assert wrong_password.status_code == 401
    assert wrong_username.status_code == 401


async def test_docs_endpoints_accessible_with_correct_credentials(
    client: AsyncClient,
):
    for path, marker in CONTENT_MARKERS.items():
        response = await client.get(
            path, auth=(settings.DOCS_USERNAME, settings.DOCS_PASSWORD)
        )
        assert response.status_code == 200, path
        assert marker in response.text.lower()


async def test_health_endpoint_remains_public(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
