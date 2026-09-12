from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts.models import UserGroupEnum

# Re-exported so pytest picks them up as fixtures/helpers for this
# directory too -- fixtures defined in a sibling package's conftest.py
# aren't inherited automatically, but importing them into this module's
# namespace makes pytest recognize them here.
from tests.test_movies.conftest import (  # noqa: F401
    certification,
    create_user_headers,
    movie_payload,
)


async def create_movie(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification_id: int,
    tag: str,
    **overrides,
) -> int:
    """Registers a one-off moderator and uses it to create a movie,
    returning the new movie's id."""
    _, mod_headers = await create_user_headers(
        client,
        db_session,
        f"mod-{tag}@example.com",
        strong_password,
        UserGroupEnum.MODERATOR,
    )
    response = await client.post(
        "/api/v1/movies",
        json=movie_payload(certification_id, name=f"Movie {tag}", **overrides),
        headers=mod_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]
