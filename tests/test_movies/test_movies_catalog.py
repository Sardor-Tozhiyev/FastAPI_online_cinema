from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts.models import UserGroupEnum
from src.movies.models import Certification
from tests.test_movies.conftest import create_user_headers, movie_payload


async def _moderator_headers(
    client: AsyncClient, db_session: AsyncSession, strong_password: str, tag: str
) -> dict[str, str]:
    _, headers = await create_user_headers(
        client,
        db_session,
        f"mod-{tag}@example.com",
        strong_password,
        UserGroupEnum.MODERATOR,
    )
    return headers


# --- Create ------------------------------------------------------------------------


async def test_moderator_can_create_movie_with_relations(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
    genre,
    director,
    star,
):
    headers = await _moderator_headers(
        client, db_session, strong_password, "create"
    )
    response = await client.post(
        "/api/v1/movies",
        json=movie_payload(
            certification.id,
            genre_ids=[genre.id],
            director_ids=[director.id],
            star_ids=[star.id],
        ),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Oppenheimer"
    assert body["certification"]["name"] == "PG-13"
    assert [g["name"] for g in body["genres"]] == ["Action"]
    assert [d["name"] for d in body["directors"]] == ["Christopher Nolan"]
    assert [s["name"] for s in body["stars"]] == ["Cillian Murphy"]
    assert body["likes_count"] == 0
    assert body["average_rating"] is None


async def test_regular_user_cannot_create_movie(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    _, headers = await create_user_headers(
        client, db_session, "plain-create@example.com", strong_password
    )
    response = await client.post(
        "/api/v1/movies",
        json=movie_payload(certification.id),
        headers=headers,
    )
    assert response.status_code == 403


async def test_create_movie_with_unknown_certification_returns_400(
    client: AsyncClient, db_session: AsyncSession, strong_password: str
):
    headers = await _moderator_headers(
        client, db_session, strong_password, "badcert"
    )
    response = await client.post(
        "/api/v1/movies",
        json=movie_payload(999999),
        headers=headers,
    )
    assert response.status_code == 400


async def test_create_movie_with_unknown_genre_returns_400(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    headers = await _moderator_headers(
        client, db_session, strong_password, "badgenre"
    )
    response = await client.post(
        "/api/v1/movies",
        json=movie_payload(certification.id, genre_ids=[999999]),
        headers=headers,
    )
    assert response.status_code == 400


async def test_create_duplicate_movie_returns_409(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    headers = await _moderator_headers(
        client, db_session, strong_password, "dup"
    )
    payload = movie_payload(certification.id, name="Duplicate")
    first = await client.post(
        "/api/v1/movies", json=payload, headers=headers
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/v1/movies", json=payload, headers=headers
    )
    assert second.status_code == 409


# --- Read ------------------------------------------------------------------------


async def test_get_movie_detail_and_404(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    headers = await _moderator_headers(
        client, db_session, strong_password, "detail"
    )
    created = await client.post(
        "/api/v1/movies",
        json=movie_payload(certification.id, name="Detail Movie"),
        headers=headers,
    )
    movie_id = created.json()["id"]

    response = await client.get(f"/api/v1/movies/{movie_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Detail Movie"

    missing = await client.get("/api/v1/movies/999999")
    assert missing.status_code == 404


# --- Update / delete ---------------------------------------------------------------


async def test_moderator_can_update_movie(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    headers = await _moderator_headers(
        client, db_session, strong_password, "update"
    )
    created = await client.post(
        "/api/v1/movies",
        json=movie_payload(certification.id, name="Update Me", price=5.0),
        headers=headers,
    )
    movie_id = created.json()["id"]

    response = await client.put(
        f"/api/v1/movies/{movie_id}",
        json={"price": 12.5},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["price"] == 12.5
    assert response.json()["name"] == "Update Me"  # untouched fields remain


async def test_regular_user_cannot_update_or_delete_movie(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    mod_headers = await _moderator_headers(
        client, db_session, strong_password, "protect"
    )
    created = await client.post(
        "/api/v1/movies",
        json=movie_payload(certification.id, name="Protected"),
        headers=mod_headers,
    )
    movie_id = created.json()["id"]

    _, user_headers = await create_user_headers(
        client, db_session, "plain-protect@example.com", strong_password
    )

    update = await client.put(
        f"/api/v1/movies/{movie_id}",
        json={"price": 1.0},
        headers=user_headers,
    )
    assert update.status_code == 403

    delete = await client.delete(
        f"/api/v1/movies/{movie_id}", headers=user_headers
    )
    assert delete.status_code == 403


async def test_moderator_can_delete_movie(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    headers = await _moderator_headers(
        client, db_session, strong_password, "delete"
    )
    created = await client.post(
        "/api/v1/movies",
        json=movie_payload(certification.id, name="Delete Me"),
        headers=headers,
    )
    movie_id = created.json()["id"]

    response = await client.delete(
        f"/api/v1/movies/{movie_id}", headers=headers
    )
    assert response.status_code == 200

    missing = await client.get(f"/api/v1/movies/{movie_id}")
    assert missing.status_code == 404

    again = await client.delete(
        f"/api/v1/movies/{movie_id}", headers=headers
    )
    assert again.status_code == 404


# --- Catalog: pagination / filter / search / sort ------------------------------------


async def _seed_catalog(
    client: AsyncClient, headers: dict[str, str], certification_id: int
) -> None:
    movies = [
        {"name": "Alpha", "year": 2010, "imdb": 6.0, "price": 5.0},
        {"name": "Beta", "year": 2015, "imdb": 7.5, "price": 15.0},
        {"name": "Gamma", "year": 2020, "imdb": 9.0, "price": 10.0},
        {"name": "Delta Heist", "year": 2020, "imdb": 8.0, "price": 20.0},
    ]
    for m in movies:
        payload = movie_payload(
            certification_id,
            name=m["name"],
            year=m["year"],
            imdb=m["imdb"],
            price=m["price"],
        )
        payload["description"] = f"A story about {m['name']}."
        if m["name"] == "Delta Heist":
            payload["description"] = "A thrilling museum heist unfolds."
        response = await client.post(
            "/api/v1/movies", json=payload, headers=headers
        )
        assert response.status_code == 201, response.text


async def test_list_movies_pagination(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    headers = await _moderator_headers(
        client, db_session, strong_password, "paginate"
    )
    await _seed_catalog(client, headers, certification.id)

    page1 = await client.get("/api/v1/movies", params={"per_page": 2, "page": 1})
    assert page1.status_code == 200
    body1 = page1.json()
    assert body1["total"] == 4
    assert body1["pages"] == 2
    assert len(body1["items"]) == 2

    page2 = await client.get("/api/v1/movies", params={"per_page": 2, "page": 2})
    body2 = page2.json()
    assert len(body2["items"]) == 2

    ids_page1 = {m["id"] for m in body1["items"]}
    ids_page2 = {m["id"] for m in body2["items"]}
    assert ids_page1.isdisjoint(ids_page2)


async def test_list_movies_filters_by_year_and_imdb(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    headers = await _moderator_headers(
        client, db_session, strong_password, "filter"
    )
    await _seed_catalog(client, headers, certification.id)

    response = await client.get(
        "/api/v1/movies",
        params={"year_from": 2015, "year_to": 2020, "imdb_min": 8.0},
    )
    assert response.status_code == 200
    names = {m["name"] for m in response.json()["items"]}
    assert names == {"Gamma", "Delta Heist"}


async def test_list_movies_search_matches_title_and_description(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    headers = await _moderator_headers(
        client, db_session, strong_password, "search"
    )
    await _seed_catalog(client, headers, certification.id)

    response = await client.get(
        "/api/v1/movies", params={"search": "heist"}
    )
    assert response.status_code == 200
    names = {m["name"] for m in response.json()["items"]}
    assert names == {"Delta Heist"}

    by_title = await client.get("/api/v1/movies", params={"search": "Alpha"})
    assert {m["name"] for m in by_title.json()["items"]} == {"Alpha"}


async def test_list_movies_search_matches_director_and_star(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
    director,
    star,
):
    headers = await _moderator_headers(
        client, db_session, strong_password, "search-people"
    )
    await client.post(
        "/api/v1/movies",
        json=movie_payload(
            certification.id, name="Nolan Film", director_ids=[director.id]
        ),
        headers=headers,
    )
    await client.post(
        "/api/v1/movies",
        json=movie_payload(
            certification.id,
            name="Murphy Film",
            year=2024,
            star_ids=[star.id],
        ),
        headers=headers,
    )

    by_director = await client.get(
        "/api/v1/movies", params={"search": "Nolan"}
    )
    assert {m["name"] for m in by_director.json()["items"]} == {"Nolan Film"}

    by_star = await client.get("/api/v1/movies", params={"search": "Murphy"})
    assert {m["name"] for m in by_star.json()["items"]} == {"Murphy Film"}


async def test_list_movies_sort_by_price(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    headers = await _moderator_headers(
        client, db_session, strong_password, "sort"
    )
    await _seed_catalog(client, headers, certification.id)

    ascending = await client.get(
        "/api/v1/movies", params={"sort_by": "price", "order": "asc"}
    )
    prices = [m["price"] for m in ascending.json()["items"]]
    assert prices == sorted(prices)

    descending = await client.get(
        "/api/v1/movies", params={"sort_by": "price", "order": "desc"}
    )
    prices_desc = [m["price"] for m in descending.json()["items"]]
    assert prices_desc == sorted(prices_desc, reverse=True)
