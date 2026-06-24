# DarkAtlas Asset Management System

A self-contained Asset Management module for the DarkAtlas Attack Surface Monitoring platform. Tracks internet-facing assets (domains, subdomains, IP addresses, services, certificates, and technologies), handles deduplication, lifecycle management, and relationship mapping.

## Tech Stack

- **Language**: Python 3.11+
- **Framework**: FastAPI
- **Database**: PostgreSQL with async SQLAlchemy (asyncpg)
- **Migrations**: Alembic
- **Testing**: Pytest
- **Containerization**: Docker & Docker Compose

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Docker & Docker Compose (optional)

### Local Development

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/darkatlas-asset-management.git
cd darkatlas-asset-management

# 2. Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.example .env
# Edit .env with your database credentials

# 5. Run database migrations
alembic upgrade head

# 6. Start the development server
uvicorn app.main:app --reload
```

### Using Docker

```bash
docker-compose up --build
```

## API Documentation

Once the server is running:

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

## Project Structure

```
app/
├── api/v1/          # Route handlers (HTTP layer)
├── core/            # Database, security, shared utilities
├── models/          # SQLAlchemy ORM models (database tables)
├── schemas/         # Pydantic schemas (request/response validation)
├── services/        # Business logic layer
├── repositories/    # Data access layer (database queries)
├── config.py        # Application settings
└── main.py          # FastAPI application entry point
tests/               # Automated tests
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://postgres:postgres@localhost:5432/darkatlas` |
| `API_KEY` | API key for write operations | `changeme` |
| `DEBUG` | Enable debug mode | `false` |

## License

This project is part of the Buguard Backend Engineering internship assessment.
