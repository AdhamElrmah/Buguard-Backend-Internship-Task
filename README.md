# DarkAtlas Asset Management System

A production-grade, self-contained Asset Management module for the **DarkAtlas Attack Surface Monitoring** platform. It tracks internet-facing assets (domains, subdomains, IP addresses, services, certificates, and technologies), handles deduplication, automates lifecycle states, and maps directed asset relationships.

---

## Tech Stack

- **Framework**: FastAPI (Async-native)
- **Database**: PostgreSQL
- **ORM**: SQLAlchemy 2.0 (Async/asyncpg)
- **Migrations**: Alembic
- **Testing**: Pytest & Pytest-Asyncio
- **Containerization**: Docker & Docker Compose (Alpine-based)

---

## Project Architecture

The project implements a **layered architecture** to separate concerns and maximize testability:
```
  [Client Request]
         │
         ▼
 ┌───────────────┐
 │  Route Layer  │  (api/v1/) Parses HTTP requests, validates auth/headers, returns JSON.
 └───────┬───────┘
         │ (Pydantic Schemas)
         ▼
 ┌───────────────┐
 │ Service Layer │  (services/) Enforces business rules (dedup, merges, lifecycle).
 └───────┬───────┘
         │ (SQLAlchemy Models)
         ▼
 ┌───────────────┐
 │ Repo Layer    │  (repositories/) Executes SQL queries asynchronously.
 └───────────────┘
```

---

## Design Decisions & Solutions

Here is how the platform resolves key architecture and data design challenges:

### 1. Database Schema & Choice
* **Decision**: PostgreSQL with SQLAlchemy Async (`asyncpg`).
* **Rationale**: PostgreSQL is the industry standard for relational systems and provides native support for array operations and JSONB document storage.
* **Tags as Array**: Tags are stored as a PostgreSQL native `TEXT[]` array with a **GIN index**. This allows fast containment queries (`tags @> ARRAY['prod']`) without creating a costly junction table.
* **Metadata as JSONB**: Stored as a `JSONB` document for flexible schema-less information (e.g. ports, banners, SSL details).

### 2. Deduplication Key & Logic
* **Deduplication Key**: `UNIQUE(type, value)`.
* **When an asset is re-imported or re-sighted**:
  - `last_seen` is automatically updated to the current time.
  - `tags` are merged using a set union (no duplicate tags are created).
  - `metadata` undergoes a **shallow merge** (new keys overwrite old ones; existing unmentioned keys are preserved).
  - `first_seen` and `created_at` are **immutable** and never modified.

### 3. Lifecycle Management
* **States**: `active` (currently sighted), `stale` (not observed recently), `archived` (manually deactivated).
* **Re-sighting Transition**: If an asset's status is `stale` and it is sighted again (imported/created), it transitions back to `active` automatically.
* **Archived Protection**: If an asset is `archived`, it will **never** be auto-reactivated. Archiving is a deliberate human decision that scanner sightings cannot override.
* **Bulk stale marking**: `POST /api/v1/assets/mark-stale` takes `threshold_days` and bulk-stales all matching assets in a single, atomic SQL query.

### 4. Differentiating Timestamps
* **Observation Timestamps**: `first_seen` and `last_seen` record real-world discovery.
* **Record Timestamps**: `created_at` and `updated_at` record database row writes.
* *Example*: Importing a 3-day-old scan report results in `first_seen` set to 3 days ago, but `created_at` set to `now`.

### 5. selectively Public API Key Security
* **Authentication**: Header-based `X-API-Key` authentication.
* **Selective Application**: Read operations (`GET`) are public to allow easy visualization and reporting. Write operations (`POST`, `PUT`, `PATCH`, `DELETE`) require the API key.

### 6. Clean Error Handling & pure Python Service Layer
* All HTTPException raising was removed from the service layer.
* Business-level failures raise custom exceptions (e.g. `NotFoundException`, `ConflictException`, `ValidationException`).
* A central Exception handler in `error_handlers.py` translates these exceptions into a standardized JSON response format.

---

## API Endpoints Overview

The API exposes the following endpoints (all write operations require the `X-API-Key` header):

### Assets
* `POST /api/v1/assets` - Create a new asset (deduplication runs on collision).
* `POST /api/v1/assets/bulk` - Bulk import assets with a partial success model (failures reported with list indices).
* `POST /api/v1/assets/mark-stale` - Bulk mark active assets as stale based on a `threshold_days` filter.
* `GET /api/v1/assets` - Paginated asset query list with optional filters (`type`, `status`, `tag`, `value` substring) and sorting (`sort_by`, `sort_order`).
* `GET /api/v1/assets/{id}` - Fetch details of a single asset.
* `PUT /api/v1/assets/{id}` - Replace all fields of an asset.
* `PATCH /api/v1/assets/{id}` - Partially update specific fields of an asset.
* `DELETE /api/v1/assets/{id}` - Hard-delete an asset and cascade-delete its relationships.

### Relationships & Graph
* `POST /api/v1/relationships` - Create a directed relationship (e.g. `belongs_to`, `resolves_to`) between two existing assets.
* `GET /api/v1/assets/{id}/relationships` - List all relationships where the asset is either the source or target.
* `GET /api/v1/assets/{id}/graph` - Retrieve the **graph around an asset**: returns the queried asset details together with all its related asset nodes, including relationship type and direction (`incoming` / `outgoing`).
* `DELETE /api/v1/relationships/{id}` - Remove a relationship.

---

## Assumptions Made
1. **Hard Deletes**: Relationships are mapped with `ON DELETE CASCADE`. Deleting an asset automatically removes all its relationships to prevent foreign key orphans.
2. **Offset Pagination**: For simple integration and paging in internal dashboards, offset-based pagination (`page` + `page_size`) was selected.
3. **No Multi-Tenancy**: The database schema assumes a single-tenant organization structure. The repository is structure-ready to adopt an `organization_id` if scaled.

---

## Environment Variables

Copy `.env.example` to `.env` and configure:

| Variable | Description | Default |
| :--- | :--- | :--- |
| `DATABASE_URL` | PostgreSQL Async connection URL | `postgresql+asyncpg://postgres:postgres123@localhost:5433/darkatlas` |
| `API_KEY` | Key required for write API operations | `testing` |
| `DEBUG` | Enables SQLAlchemy query logs and debug mode | `true` |
| `HOST` | Dev server interface | `0.0.0.0` |
| `PORT` | Dev server port | `8000` |

---

## Getting Started

### Local Setup (Windows / Linux)

1. **Activate Virtual Environment**:
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On Linux/Mac:
   source venv/bin/activate
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Database Migrations**:
   Ensure you have a PostgreSQL instance running, configure your `.env` connection string, and run:
   ```bash
   alembic upgrade head
   ```

4. **Start Development Server**:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   Open [http://localhost:8000/docs](http://localhost:8000/docs) to access the interactive Swagger UI.

---

### Docker Setup (Compose)

1. **Start the Stack**:
   Ensure Docker Desktop is running, then execute:
   ```bash
   docker compose up --build -d
   ```
2. **What this does**:
   - Downloads and starts a healthy `postgres:15-alpine` container on port `5434`.
   - Builds the Alpine-based API container.
   - Waits for the database to be healthy, runs database migrations, and starts the FastAPI server.
3. **Interact**:
   Open [http://localhost:8000/docs](http://localhost:8000/docs) (API Key: `testing` or your configured key).
4. **Shutdown**:
   ```bash
   docker compose down
   ```

---

## Running Automated Tests

Tests run against a dedicated test database (`darkatlas_test`). 

1. **Create the test database** in PostgreSQL:
   ```sql
   CREATE DATABASE darkatlas_test;
   ```
2. **Execute Pytest**:
   ```bash
   venv\Scripts\pytest
   ```
   All 16 tests covering CRUD, bulk imports, lifecycle management, and relationships will run sequentially.
