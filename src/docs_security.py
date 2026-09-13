import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from config import settings

security = HTTPBasic()


def require_docs_access(
    credentials: HTTPBasicCredentials = Depends(security),
) -> str:
    """Dependency guarding /docs, /redoc and /openapi.json.

    Uses a separate HTTP Basic username/password (`DOCS_USERNAME` /
    `DOCS_PASSWORD`) rather than the app's own JWT auth, since a browser
    hitting these routes directly has no bearer token to send. Comparisons
    use `secrets.compare_digest` to avoid leaking credential length/content
    through response-time differences.
    """
    correct_username = secrets.compare_digest(
        credentials.username, settings.DOCS_USERNAME
    )
    correct_password = secrets.compare_digest(
        credentials.password, settings.DOCS_PASSWORD
    )
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials for API documentation.",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
