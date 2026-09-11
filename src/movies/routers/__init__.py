from src.movies.routers.comments import router as comments_router
from src.movies.routers.directors import router as directors_router
from src.movies.routers.genres import router as genres_router
from src.movies.routers.interactions import router as interactions_router
from src.movies.routers.movies import router as movies_router
from src.movies.routers.stars import router as stars_router


routers = [
    movies_router,
    genres_router,
    stars_router,
    directors_router,
    interactions_router,
    comments_router,
]
