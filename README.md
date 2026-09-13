# Online Cinema

Digital platform for browsing, purchasing, and watching movies online. Built with
FastAPI (async), PostgreSQL, Celery/Redis, MinIO (S3-compatible storage), and Stripe.

## Project status / roadmap

This repository is built incrementally, one feature branch at a time:

| Branch                 | Scope                                                     | Status |
| ---------------------- | --------------------------------------------------------- | ------ |
| `project-setup`        | Repo skeleton, Docker, Poetry, CI, base app               | ✅ done |
| `accounts-auth`        | Registration, activation, JWT auth, roles                 | ✅ done |
| `movies-catalog`       | Movies, genres, actors, directors, search/filter          | ✅ done |
| `shopping-cart`        | Cart CRUD                                                 | ✅ done |
| `orders`               | Order placement & lifecycle                               | ✅ done |
| `payments-stripe`      | Stripe checkout & webhooks                                | ✅ done |
| `restrict-docs-access` | Gate `/docs`, `/redoc`, `/openapi.json` behind HTTP Basic | ✅ done |

## Tech stack

* Python 3.13
* FastAPI
* SQLAlchemy 2.0 (async)
* PostgreSQL 16
* Alembic
* Celery + Redis
* MinIO (S3-compatible object storage)
* Stripe
* Poetry
* Docker / Docker Compose
* Nginx
* pytest / pytest-asyncio / pytest-cov
* flake8
* Black
* mypy
* GitHub Actions
* AWS EC2

## Getting started

### With Docker (recommended)

Create a local environment file:

```bash
cp .env.example .env
```

Then start the application:

```bash
docker compose up --build
```

The following services are started:

* `app` — FastAPI application on port `8000`
* `db` — PostgreSQL
* `redis` — Redis
* `celery_worker` — Celery background worker
* `celery_beat` — scheduled Celery tasks
* `minio` — S3-compatible object storage
* `mailhog` — local email testing server

MailHog Web UI is available at:

```text
http://localhost:8025
```

MinIO Console is available at:

```text
http://localhost:9001
```

### API documentation

Interactive API documentation is protected with HTTP Basic Authentication.

Swagger UI:

```text
http://localhost:8000/docs
```

ReDoc:

```text
http://localhost:8000/redoc
```

OpenAPI schema:

```text
http://localhost:8000/openapi.json
```

Documentation access credentials are configured through the environment variables
defined in `.env.example`.

The documentation authentication is separate from the application's JWT authentication.

### Health check

The application exposes a public health endpoint:

```text
GET /health
```

Example:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

## Locally with Poetry

Install dependencies:

```bash
poetry install
```

Create the environment file:

```bash
cp .env.example .env
```

Adjust `DATABASE_URL` and other environment variables for the local environment.

Run the application:

```bash
poetry run uvicorn src.main:app --reload
```

## Running tests

Run the complete test suite with coverage:

```bash
poetry run pytest --cov=src --cov-report=term-missing
```

Tests use an in-memory SQLite database where possible, so the test suite does not
require a production PostgreSQL instance.

The current test suite covers:

* user registration and activation
* activation token resend
* login / refresh / logout
* password change
* password reset
* role-based access control
* movies catalog
* genres
* actors and directors
* search, filtering and sorting
* reactions
* 10-point ratings
* favorites
* nested comments
* shopping cart
* per-user cart isolation
* moderator visibility
* movie deletion cart protection
* order placement
* order lifecycle
* order cancellation
* moderator order listing and filtering
* Stripe checkout sessions
* Stripe webhook handling
* payment history
* refunds
* administrator order/payment listing
* protected API documentation

The Stripe SDK is isolated behind a thin wrapper, allowing the tests to run without
calling the real Stripe API.

## Database migrations

Database schema changes are managed exclusively with Alembic.

Create a new migration after changing SQLAlchemy models:

```bash
poetry run alembic revision --autogenerate -m "add xyz table"
```

Apply migrations:

```bash
poetry run alembic upgrade head
```

Check the current database revision:

```bash
poetry run alembic current
```

Check the latest available revision:

```bash
poetry run alembic heads
```

The production database on AWS EC2 is migrated explicitly during deployment before
the application is restarted.

The Alembic environment imports all modules containing SQLAlchemy models so that
`Base.metadata` contains the complete schema during autogeneration.

## API documentation — Accounts module (`/api/v1/accounts`)

Full request/response schemas are available through the protected Swagger UI.

| Method & Path                    | Auth         | Description                                                     |
| -------------------------------- | ------------ | --------------------------------------------------------------- |
| `POST /register`                 | —            | Registers a new user and sends an activation email.             |
| `POST /activate`                 | —            | Activates a user account using an activation token.             |
| `POST /resend-activation`        | —            | Generates and sends a new activation token.                     |
| `POST /login`                    | —            | Authenticates an active user and returns access/refresh tokens. |
| `POST /refresh`                  | —            | Creates a new access token from a valid refresh token.          |
| `POST /logout`                   | —            | Revokes a refresh token.                                        |
| `GET /me`                        | Bearer token | Returns the authenticated user's profile.                       |
| `POST /change-password`          | Bearer token | Changes the authenticated user's password.                      |
| `POST /password-reset/request`   | —            | Requests a password reset token.                                |
| `POST /password-reset/confirm`   | —            | Resets a password using a valid reset token.                    |
| `PATCH /users/{user_id}/group`   | ADMIN        | Changes a user's role.                                          |
| `POST /users/{user_id}/activate` | ADMIN        | Manually activates a user account.                              |

### Roles

* **USER** — base catalog and application access.
* **MODERATOR** — USER permissions plus movie, genre, actor management and sales visibility.
* **ADMIN** — MODERATOR permissions plus user management.

## Background jobs

Celery Beat runs scheduled maintenance tasks, including:

* cleanup of expired activation tokens
* cleanup of expired password reset tokens

Celery Worker processes asynchronous background jobs.

## Production deployment

The application is deployed to an AWS EC2 Ubuntu 24.04 instance using Docker Compose.

Production architecture:

```text
Internet
   |
   | HTTP :80 / HTTPS :443
   v
 Nginx
   |
   | reverse proxy
   v
FastAPI :8000
   |
   +-----------------------------+
   |                             |
   v                             v
PostgreSQL                    Redis
   |                             |
   +-----------------------------+
   |
   +-- MinIO
   |
   +-- MailHog
   |
   +-- Celery Worker
   |
   +-- Celery Beat
```

The application source code is deployed on the EC2 instance at:

```text
/home/ubuntu/src/FastAPI_online_cinema
```

Nginx acts as a reverse proxy and forwards incoming HTTP requests to the FastAPI
application.

The AWS Security Group exposes HTTP/HTTPS and SSH. Internal application services
such as PostgreSQL, Redis and MinIO are not exposed through the AWS Security Group.

### Production environment

Production environment variables are stored in `.env` directly on the EC2 instance.

The `.env` file is intentionally excluded from Git:

```text
.env
```

Production secrets are therefore not committed to the repository.

## Continuous Integration

GitHub Actions runs the CI pipeline on pushes and pull requests.

The pipeline performs:

1. dependency installation
2. flake8 linting
3. Black formatting check
4. mypy type checking
5. pytest test suite
6. test coverage generation
7. coverage artifact upload

The CI pipeline uses Python 3.13 and Poetry.

## Continuous Deployment

Successful pushes to the `main` branch trigger deployment to AWS EC2 after all CI
checks pass.

The deployment process:

```text
git push main
      |
      v
GitHub Actions
      |
      v
Lint
      |
      v
Black
      |
      v
mypy
      |
      v
pytest
      |
      v
SSH to AWS EC2
      |
      v
git pull origin main
      |
      v
docker compose up -d --build
      |
      v
alembic upgrade head
      |
      v
restart FastAPI
```

The deployment connects to EC2 using GitHub Actions secrets:

```text
EC2_HOST
EC2_USERNAME
EC2_SSH_KEY
```

The production `.env` file is not transferred through GitHub Actions.

## Security considerations

The following files and secrets must never be committed to Git:

```text
.env
*.pem
*.key
```

Production secrets such as JWT keys and Stripe credentials must be stored outside
the repository.

The API documentation is protected with HTTP Basic Authentication.

The AWS Security Group should expose only the ports required for the public
application and administration.

## Repository structure

```text
FastAPI_online_cinema/
├── .github/
│   └── workflows/
├── alembic/
│   ├── versions/
│   └── env.py
├── src/
│   ├── accounts/
│   ├── cart/
│   ├── movies/
│   ├── orders/
│   ├── payments/
│   ├── celery_app/
│   ├── config.py
│   ├── database.py
│   └── main.py
├── tests/
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── docker-entrypoint.sh
├── poetry.lock
├── pyproject.toml
└── README.md
```

## License

This project is developed as a backend engineering portfolio project.
