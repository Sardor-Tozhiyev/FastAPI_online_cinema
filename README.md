# FastAPI Online Cinema

A backend REST API for an online cinema platform built with FastAPI.

The project provides user authentication, movie management, shopping cart functionality, orders, payments, background tasks, object storage, and administrative functionality.

## Project Status

The application is deployed to an AWS EC2 instance using Docker Compose.

The production deployment includes:

* FastAPI
* PostgreSQL
* Redis
* Celery worker
* Celery Beat
* MinIO
* MailHog
* Nginx
* GitHub Actions CI/CD

The application is currently available over HTTP through the EC2 public IP.

## Tech Stack

* **Python 3.13**
* **FastAPI**
* **SQLAlchemy 2.0**
* **Alembic**
* **PostgreSQL 16**
* **Redis 7**
* **Celery**
* **Pydantic**
* **JWT authentication**
* **Stripe**
* **MinIO / S3-compatible storage**
* **MailHog**
* **Docker / Docker Compose**
* **Nginx**
* **Poetry**
* **pytest**
* **pytest-cov**
* **flake8**
* **Black**
* **mypy**
* **GitHub Actions**
* **AWS EC2**

## Main Features

### Authentication

* User registration
* JWT authentication
* Access and refresh tokens
* Email activation
* Password reset
* Password change
* Role-based access control

### Movies

* Movie creation
* Movie listing
* Movie details
* Movie updating
* Movie deletion
* Filtering and pagination
* Movie certifications

### Shopping Cart

* Add movies to cart
* Remove movies from cart
* Update cart items
* View current cart

### Orders

* Create orders from the shopping cart
* Order history
* Order details
* Order filtering
* Administrative order management

### Payments

* Stripe payment integration
* Payment status handling
* Stripe webhook support

### Background Tasks

Celery is used for asynchronous and scheduled tasks.

The deployment includes:

* Celery Worker
* Celery Beat
* Redis as the message broker

### File Storage

MinIO provides S3-compatible object storage for application files.

### Email

MailHog is used as a development/testing SMTP server.

## Project Structure

```text
FastAPI_online_cinema/
├── alembic/
│   ├── versions/
│   └── env.py
├── src/
│   ├── accounts/
│   ├── cart/
│   ├── celery_app/
│   ├── movies/
│   ├── orders/
│   ├── payments/
│   ├── ...
│   └── main.py
├── tests/
├── .github/
│   └── workflows/
├── .env.example
├── .gitignore
├── alembic.ini
├── docker-compose.yml
├── docker-entrypoint.sh
├── Dockerfile
├── poetry.lock
├── pyproject.toml
└── README.md
```

## Requirements

For local development:

* Python 3.13
* Poetry
* Docker
* Docker Compose

## Local Development

Clone the repository:

```bash
git clone https://github.com/Sardor-Tozhiyev/FastAPI_online_cinema.git
cd FastAPI_online_cinema
```

Install dependencies:

```bash
poetry install
```

Create the environment file:

```bash
cp .env.example .env
```

Update `.env` with the required local configuration.

Start the infrastructure services:

```bash
docker compose up -d
```

Apply database migrations:

```bash
poetry run alembic upgrade head
```

Run the application:

```bash
poetry run uvicorn src.main:app --reload
```

The application will be available at:

```text
http://127.0.0.1:8000
```

## Docker Compose

The project provides a complete Docker Compose environment.

Start all services:

```bash
docker compose up -d --build
```

Check service status:

```bash
docker compose ps
```

View application logs:

```bash
docker compose logs app
```

Follow application logs:

```bash
docker compose logs -f app
```

Stop the services:

```bash
docker compose down
```

## Database Migrations

Alembic is used for database migrations.

Check the current migration:

```bash
alembic current
```

Show available migration heads:

```bash
alembic heads
```

Apply all migrations:

```bash
alembic upgrade head
```

Create a new migration:

```bash
alembic revision --autogenerate -m "migration description"
```

When deploying to EC2, database migrations should be applied after updating the application code.

## API Documentation

FastAPI provides interactive API documentation.

Depending on the application environment and documentation access settings:

```text
/docs
/redoc
```

The documentation endpoints are protected by the application's documentation access dependency.

## Health Check

The application provides a health endpoint:

```text
GET /health
```

Example response:

```json
{
  "status": "ok"
}
```

The endpoint can be used to verify that the application is running correctly.

## Testing

Run the test suite:

```bash
poetry run pytest
```

Run tests with coverage:

```bash
poetry run pytest --cov=src --cov-report=term-missing
```

## Code Quality

### Flake8

```bash
poetry run flake8 src tests --max-line-length=100 --extend-ignore=E203,W503
```

### Black

Check formatting:

```bash
poetry run black --check src tests
```

Format the project:

```bash
poetry run black src tests
```

### Mypy

```bash
poetry run mypy src
```

## Continuous Integration

GitHub Actions automatically runs checks for pushes and pull requests.

The CI pipeline includes:

1. Installing Python 3.13
2. Installing Poetry
3. Installing project dependencies
4. Running flake8
5. Checking Black formatting
6. Running mypy
7. Running pytest
8. Generating test coverage
9. Uploading the coverage report

The CI workflow must pass before the deployment job runs.

## Continuous Deployment

The project uses GitHub Actions for automatic deployment to AWS EC2.

Deployment is triggered automatically after a successful CI run when changes are pushed to the `main` branch.

The deployment process:

1. GitHub Actions runs linting, formatting, type checking, and tests.
2. GitHub Actions connects to the EC2 server through SSH.
3. The latest `main` branch is pulled on the server.
4. Docker Compose rebuilds the application containers.
5. The updated services are started.

The application is deployed to:

```text
/home/ubuntu/src/FastAPI_online_cinema
```

The EC2 deployment uses GitHub Actions secrets:

```text
EC2_HOST
EC2_USERNAME
EC2_SSH_KEY
```

These values must be configured as GitHub repository secrets and must never be committed to the repository.

## Production Architecture

The current production architecture is:

```text
Internet
   │
   ▼
AWS EC2
   │
   ▼
Nginx :80
   │
   ▼
FastAPI :8000
   │
   ├── PostgreSQL
   ├── Redis
   ├── Celery Worker
   ├── Celery Beat
   ├── MinIO
   └── MailHog
```

Nginx acts as a reverse proxy in front of the FastAPI application.

The application is currently served over HTTP using the EC2 public IP.

No custom domain or HTTPS/SSL configuration is currently used.

## EC2 Deployment

The EC2 server runs Ubuntu 24.04.

The project is located at:

```text
/home/ubuntu/src/FastAPI_online_cinema
```

Useful commands on the server:

```bash
cd /home/ubuntu/src/FastAPI_online_cinema
```

Check running services:

```bash
docker compose ps
```

Check application logs:

```bash
docker compose logs app --tail=50
```

Check Nginx:

```bash
sudo systemctl status nginx --no-pager
```

Check the application through Nginx:

```bash
curl -i http://127.0.0.1/health
```

Check the public endpoint:

```bash
curl -i http://<EC2_PUBLIC_IP>/health
```

## Environment Variables

Production environment variables are stored directly on the EC2 server in `.env`.

The `.env` file is excluded from Git using `.gitignore`.

Sensitive values such as:

* JWT secret
* Stripe secret key
* Stripe webhook secret
* S3 credentials
* database credentials

must not be committed to GitHub.

Use `.env.example` as a template for required environment variables.

## Security Considerations

Production secrets must never be stored in the repository.

GitHub Actions deployment credentials are stored using GitHub encrypted secrets.

The EC2 instance uses AWS Security Groups to control inbound traffic.

The public application entry point is Nginx on port `80`.

Internal services such as PostgreSQL, Redis, MinIO, and MailHog are not intended to be accessed directly from the public Internet.

## Useful Commands

Check all Docker containers:

```bash
docker ps
```

Check Compose services:

```bash
docker compose ps
```

Restart the application:

```bash
docker compose restart app
```

Rebuild and restart:

```bash
docker compose up -d --build
```

View all logs:

```bash
docker compose logs --tail=100
```

Check Nginx configuration:

```bash
sudo nginx -t
```

Reload Nginx:

```bash
sudo systemctl reload nginx
```

## License

This project is intended for educational and portfolio purposes.
