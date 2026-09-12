# Online Cinema

Digital platform for browsing, purchasing, and watching movies online. Built with
FastAPI (async), PostgreSQL, Celery/Redis, MinIO (S3-compatible storage), and Stripe.

## Project status / roadmap

This repository is built incrementally, one feature branch at a time:

| Branch            | Scope                                                               | Status |
|-------------------|---------------------------------------------------------------------|--------|
| `project-setup`   | Repo skeleton, Docker, Poetry, CI, base app                         | ✅ done |
| `accounts-auth`   | Registration, activation, JWT auth, roles                           | ✅ done |
| `movies-catalog`  | Movies, genres, actors, directors, search/filter                    | ✅ done |
| `shopping-cart`   | Cart CRUD                                                           | ✅ done |
| `orders`          | Order placement & lifecycle                                         | ✅ done |
| `payments-stripe` | Stripe checkout & webhooks                                          | planned |

## Getting started

### With Docker (recommended)

```bash
cp .env.example .env
docker compose up --build
```

This starts: `app` (FastAPI on :8000), `db` (Postgres), `redis`, `celery_worker`,
`celery_beat` (periodic cleanup of expired tokens), `minio` (S3-compatible storage on
:9000 / console :9001), and `mailhog` (catches outgoing emails, inspect at
http://localhost:8025).

Interactive API docs (Swagger UI): **http://localhost:8000/docs**
ReDoc: **http://localhost:8000/redoc**

### Locally with Poetry

```bash
poetry install
cp .env.example .env   # adjust DATABASE_URL etc. to point at a local Postgres, or use sqlite for a quick spin
poetry run uvicorn src.main:app --reload
```

### Running tests

```bash
poetry run pytest --cov=src --cov-report=term-missing
```

Tests use an in-memory SQLite database (see `tests/conftest.py`), so no external
services are required to run the suite. 94 tests currently cover accounts (registration,
activation/resend, login/refresh/logout, password change/reset, role-based access),
movies (catalog CRUD/search/filter/sort, genres/stars/directors, reactions, 10-point
ratings, favorites, nested comments), the shopping cart (add/remove/clear, per-user
scoping, moderator visibility, delete-movie cart guard), and orders (placement from
cart with purchased/pending exclusion rules, listing/detail/cancellation, moderator
admin listing with filters).

### Database migrations

```bash
poetry run alembic revision --autogenerate -m "add xyz table"
poetry run alembic upgrade head
```

## API documentation — Accounts module (`/api/v1/accounts`)

Full request/response schemas are always available live via Swagger (`/docs`); below is
a narrative summary of what each custom endpoint does and why.

| Method & Path | Auth | Description |
|---|---|---|
| `POST /register` | — | Registers a new user (`email`, `password`). Password must satisfy the complexity policy (≥8 chars, upper/lower/digit/special char). Creates the user **inactive**, issues a 24h `ActivationToken`, and sends an activation email with a link `FRONTEND_URL/activate?email=...&token=...`. 409 if the email is taken. |
| `POST /activate` | — | Body: `email`, `token`. Activates the account if the token matches and hasn't expired. Deletes the token on success. 400 on invalid/expired token. |
| `POST /resend-activation` | — | Body: `email`. Issues a fresh 24h token (invalidating the old one) and resends the email. Always returns 200 with a generic message to avoid leaking whether an email is registered. |
| `POST /login` | — | Body: `email`, `password`. Requires an **active** account. Returns a JWT `access_token` (15 min TTL) and `refresh_token` (7 days TTL, persisted server-side so it can be revoked). |
| `POST /refresh` | — | Body: `refresh_token`. Returns a new `access_token` if the refresh token is valid, unexpired, and not revoked. |
| `POST /logout` | — | Body: `refresh_token`. Deletes the stored refresh token, revoking that session. |
| `GET /me` | Bearer access token | Returns the authenticated user's profile. |
| `POST /change-password` | Bearer access token | Body: `old_password`, `password` (new). Verifies the old password, validates the new one against the complexity policy, updates the hash. |
| `POST /password-reset/request` | — | Body: `email`. If the account exists and is active, issues a `PasswordResetToken` and emails a reset link. Always returns a generic 200 to prevent account enumeration. |
| `POST /password-reset/confirm` | — | Body: `email`, `token`, `password` (new). Sets the new password without requiring the old one, if the token is valid and unexpired. Token is single-use. |
| `PATCH /users/{user_id}/group` | Bearer access token, **ADMIN only** | Body: `{"group": "USER" \| "MODERATOR" \| "ADMIN"}`. Reassigns a user's role. 403 for non-admins. |
| `POST /users/{user_id}/activate` | Bearer access token, **ADMIN only** | Manually marks a user as active (e.g., support workaround), deleting any pending activation token. |

### Roles

- **USER** — base catalog/interface access.
- **MODERATOR** — everything USER has, plus movie/genre/actor CRUD and sales visibility (movie/genre/actor CRUD implemented in `feature/movies-catalog`; sales visibility lands with `feature/orders`).
- **ADMIN** — everything MODERATOR has, plus user management (`/users/{id}/group`, `/users/{id}/activate`).

### Background jobs (Celery Beat)

- `accounts.cleanup_expired_activation_tokens` — hourly, deletes expired `ActivationToken` rows.
- `accounts.cleanup_expired_password_reset_tokens` — hourly, deletes expired `PasswordResetToken` rows.

## Tech stack

FastAPI · SQLAlchemy 2.0 (async) · PostgreSQL · Alembic · Celery + Redis · MinIO ·
Stripe · Poetry · Docker Compose · pytest/pytest-asyncio/pytest-cov · GitHub Actions CI
(flake8, black, mypy, pytest+coverage, deploy to EC2 on `main`).
