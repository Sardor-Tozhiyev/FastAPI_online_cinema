"""Aggregates the movies module's sub-routers into a single APIRouter.

Order matters: `interactions` defines the literal route
`GET /api/v1/movies/favorites`, which must be registered before `movies`'s
`GET /api/v1/movies/{movie_id}` -- otherwise the latter would swallow
`/favorites` as an (invalid) movie id. `comments` and `genres`/`stars`/
`directors` use extra path segments or distinct prefixes, so they aren't
order-sensitive, but are kept alongside for readability.
"""

from fastapi import APIRouter

from src.movies.routers import comments, directors, genres, interactions
from src.movies.routers import movies as movies_router_module
from src.movies.routers import stars

router = APIRouter()

router.include_router(interactions.router)
router.include_router(comments.router)
router.include_router(genres.router)
router.include_router(stars.router)
router.include_router(directors.router)
router.include_router(movies_router_module.router)
