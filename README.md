# CloudKey PMS Server

A modern, high-performance, asynchronous Property Management System (PMS) backend built with **FastAPI**, **SQLAlchemy 2.0 (asyncio)**, **Pydantic v2**, and **Supabase / PostgreSQL**.

---

## 🌟 Key Features

- **Multi-Tenant Architecture**: Organization-level isolation with Property and Room-level hierarchy.
- **RBAC & User Access Management**: Organizations and Properties with user assignment, roles, and granular permissions (`organization_users`, `property_users`, `roles`, `permissions`, `role_permissions`).
- **Async SQLAlchemy 2.0**: Full async database operations with PostgreSQL (`asyncpg`) and SQLite (`aiosqlite`) fallback.
- **Supabase Ready**: Direct connection or Supabase Connection Pooler support with JWT authorization hooks.
- **Strict Data Contracts**: Pydantic v2 request/response schemas with automated OpenAPI docs.
- **Layered Architecture**: Clear separation of `models`, `schemas`, `crud`, `services`, `routes`, `dependencies`, and `middleware`.
- **Database Migrations**: Alembic async setup for schema migrations.
- **Automated Tests**: Pytest test suite with in-memory SQLite fixtures and HTTPX AsyncClient.

---

## 📁 Project Structure

```text
cloudkey-server/
├── app/
│   ├── main.py                          # FastAPI app entrypoint, CORS, lifespan & error handlers
│   ├── config.py                        # Pydantic BaseSettings & environment variables
│   ├── database.py                      # Async SQLAlchemy engine, sessionmaker & Base model
│   │
│   ├── models/                          # SQLAlchemy 2.0 declarative database models
│   │   ├── __init__.py
│   │   ├── user.py                      # User account entity (email, password, profile)
│   │   ├── organization.py              # Tenant / Organization entity
│   │   ├── property.py                  # Property entity (hotel, resort, etc.)
│   │   ├── room_type.py                 # Room classification (occupancies, status)
│   │   ├── room.py                      # Physical room instances & room status
│   │   ├── rate_plan.py                 # Rate plans & booking types (NIGHTLY / HOURLY)
│   │   ├── rate_plan_rate.py            # Calendar pricing intervals, durations & occupancies
│   │   ├── property_booking_settings.py # Check-in/out times, hourly/nightly booking rules
│   │   ├── role.py                      # Role, Permission & role_permissions tables
│   │   ├── organization_user.py         # Organization user membership & roles
│   │   └── property_user.py             # Property user membership & roles
│   │
│   ├── schemas/                         # Pydantic v2 schemas (Create, Update, Response)
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── auth.py
│   │   ├── organization.py
│   │   ├── property.py
│   │   ├── property_setup.py            # Setup wizard & dashboard contracts
│   │   ├── room_type.py
│   │   ├── room.py
│   │   ├── rate_plan.py
│   │   ├── rate_plan_rate.py
│   │   ├── property_booking_settings.py
│   │   ├── role.py
│   │   ├── organization_user.py
│   │   └── property_user.py
│   │
│   ├── routes/                          # FastAPI REST API endpoints
│   │   ├── __init__.py                  # Aggregated api_router (/api/v1)
│   │   ├── auth.py                      # /api/v1/auth/signup, /login, /me
│   │   ├── organization.py              # /api/v1/organizations
│   │   ├── properties.py                # /api/v1/properties
│   │   ├── property_setup.py            # /api/v1/properties/{id}/setup/*, /dashboard
│   │   ├── room_types.py                # /api/v1/room-types
│   │   ├── rooms.py                     # /api/v1/rooms
│   │   ├── rate_plans.py                # /api/v1/rate-plans
│   │   ├── property_booking_settings.py # /api/v1/booking-settings
│   │   ├── roles.py                     # /api/v1/roles, /api/v1/roles/permissions
│   │   ├── organization_users.py        # /api/v1/organization-users
│   │   └── property_users.py            # /api/v1/property-users
│   │
│   ├── crud/                            # Database access & repositories
│   │   ├── __init__.py
│   │   ├── base.py                      # Reusable generic CRUDBase repository
│   │   ├── organization.py
│   │   ├── property.py
│   │   ├── room_type.py
│   │   ├── room.py
│   │   ├── rate_plan.py
│   │   ├── rate_plan_rate.py
│   │   ├── property_booking_settings.py
│   │   ├── role.py
│   │   ├── organization_user.py
│   │   └── property_user.py
│   │
│   ├── services/                        # Business logic layer
│   │   ├── __init__.py
│   │   ├── organization_service.py
│   │   ├── property_service.py
│   │   ├── room_type_service.py
│   │   ├── room_service.py
│   │   ├── rate_plan_service.py
│   │   ├── booking_settings_service.py
│   │   ├── role_service.py
│   │   └── user_access_service.py
│   │
│   ├── dependencies/                    # FastAPI dependency injection
│   │   ├── __init__.py
│   │   ├── auth.py                      # Supabase JWT decoder & dev mode user
│   │   └── tenant.py                    # Multi-tenant extractor (X-Organization-ID header)
│   │
│   ├── utils/                           # Utilities & helpers
│   │   ├── __init__.py
│   │   ├── enums.py                     # RoomStatus, BookingType, RoleScope, etc.
│   │   ├── validators.py                # String & slug sanitation
│   │   └── exceptions.py                # Domain exceptions & error handlers
│   │
│   └── middleware/                      # HTTP middlewares
│       ├── __init__.py
│       └── tenant_middleware.py         # Request-ID, process timing, tenant context
│
├── migrations/                          # Alembic database migrations
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       ├── d68d12980896_create_pms_schema.py
│       └── f01976405b0a_add_roles_and_user_access_tables.py
├── tests/                               # Pytest test suite
│   ├── __init__.py
│   ├── conftest.py                      # In-memory DB session & AsyncClient fixtures
│   ├── test_organizations.py
│   ├── test_properties.py
│   ├── test_room_types.py
│   ├── test_rooms.py
│   ├── test_rate_plans.py
│   ├── test_booking_settings.py
│   └── test_roles_and_users.py
├── .env                                 # Environment variables (configured for local & Supabase)
├── .env.example
├── .gitignore
├── alembic.ini                          # Alembic configuration
├── requirements.txt                     # Dependencies
└── README.md
```

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+
- Activated virtual environment `venv`

### 2. Environment Setup
The project is preconfigured with a `.env` file. By default, it uses SQLite (`sqlite+aiosqlite:///./pms.db`) so that you can run and test immediately without configuring a database server.

#### Configuring Supabase (PostgreSQL)
To connect to your **Supabase** instance:
1. Open your Supabase Dashboard -> **Project Settings** -> **Database**.
2. Copy the **Connection String** (URI) and format it for `asyncpg`:
   ```bash
   # Direct connection:
   DATABASE_URL="postgresql+asyncpg://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres"

   # Or Supabase Transaction Pooler (recommended for serverless/high concurrency):
   DATABASE_URL="postgresql+asyncpg://postgres.[YOUR-PROJECT-REF]:[YOUR-PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres"
   ```
3. Set your Supabase API keys in `.env`:
   ```bash
   SUPABASE_URL="https://[YOUR-PROJECT-REF].supabase.co"
   SUPABASE_KEY="[YOUR-ANON-OR-SERVICE-KEY]"
   SUPABASE_JWT_SECRET="[YOUR-JWT-SECRET]"
   ```

### 3. Install Dependencies
```bash
# Windows PowerShell
.\venv\Scripts\pip install -r requirements.txt
```

### 4. Run Database Migrations
```bash
.\venv\Scripts\alembic upgrade head
```

### 5. Start Development Server
```bash
.\venv\Scripts\uvicorn app.main:app --reload --port 8000
```
- Interactive Swagger UI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Alternative ReDoc UI: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- Health Check: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

---

## 🧪 Running Automated Tests

Run the full pytest suite:
```bash
.\venv\Scripts\pytest -v
```

All 9 test suites test every entity's CRUD lifecycle and access controls using in-memory async SQLite sessions.
