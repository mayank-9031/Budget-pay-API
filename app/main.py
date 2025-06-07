# app/main.py
import uvicorn
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import engine, Base
from app.core.auth import (
    fastapi_users,
    auth_backend,
    UserRead,
    UserCreate,
    UserUpdate,
)
from app.api.v1.routes import (
    users,
    categories,
    expenses,
    transactions,
    goals,
    dashboard,
)

# Create all tables on startup (for MVP—later, use Alembic migrations)
async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

app = FastAPI(
    title="Budget Pay API",
    version="0.1.0",
    openapi_url="/openapi.json",
)

# CORS Configuration
origins = [
    "http://localhost:3000",            # Next.js dev server (local)
    "http://localhost:3001",            # Alternative local port
    settings.FRONTEND_URL,              # Production frontend URL from settings
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if settings.FRONTEND_URL and "onrender.com" in settings.FRONTEND_URL:
    origins.append("https://*.onrender.com")

# ------------------------------------------------------------
# AUTHENTICATION ROUTES (Mount only once here)
# ------------------------------------------------------------

# 1. JWT Authentication (login/logout) - SINGLE ENDPOINT
app.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/api/v1/auth/jwt",
    tags=["Authentication"],
)

# 2. Registration - SINGLE ENDPOINT
app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/api/v1/auth",
    tags=["Authentication"],
)

# 3. User Management (me, update profile, etc.) - SINGLE ENDPOINT
app.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/api/v1/users",
    tags=["User Management"],
)

# ------------------------------------------------------------
# ROOT ENDPOINT
# ------------------------------------------------------------
@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "Budget Pay API is running!",
        "version": "0.1.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "endpoints": {
            "register": "/api/v1/auth/register",
            "login": "/api/v1/auth/jwt/login",
            "logout": "/api/v1/auth/jwt/logout",
            "profile": "/api/v1/users/me"
        }
    }

# ------------------------------------------------------------
# BUSINESS LOGIC ROUTES
# ------------------------------------------------------------
app.include_router(users.router, prefix="/api/v1")
app.include_router(categories.router, prefix="/api/v1")
app.include_router(expenses.router, prefix="/api/v1")
app.include_router(transactions.router, prefix="/api/v1")
app.include_router(goals.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")

# ------------------------------------------------------------
# STARTUP EVENT
# ------------------------------------------------------------
@app.on_event("startup")
async def on_startup():
    await create_db_and_tables()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)