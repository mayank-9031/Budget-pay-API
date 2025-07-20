# app/main.py
import uvicorn
import os
import logging
from fastapi import FastAPI, HTTPException, Form, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from app.core.auth import current_active_user, get_user_manager, UserManager
from fastapi.responses import JSONResponse
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
    dashboard,
    chatbot,
    google_auth,
    auth,
    notification,
    goals,
)
from fastapi.openapi.utils import get_openapi

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create all tables on startup (for MVP—later, use Alembic migrations)
async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

app = FastAPI(
    title="Budget Pay API",
    version="1.1.0",
    description="""
    
    """,
    openapi_url="/openapi.json",
    openapi_tags=[
        {"name": "Authentication", "description": "Operations related to authentication"},
        {"name": "Google Authentication", "description": "Google OAuth authentication endpoints"},
        {"name": "User Management", "description": "User profile and settings operations"},
    ],
)

# Add custom security schemes for OpenAPI documentation
app.openapi_schema = None  # Clear any existing schema

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    
    # Add both OAuth2 password flow and Bearer token authentication
    openapi_schema["components"]["securitySchemes"] = {
        "OAuth2PasswordBearer": {
            "type": "oauth2",
            "flows": {
                "password": {
                    "tokenUrl": "/api/v1/auth/jwt/login",
                    "scopes": {}
                }
            }
        },
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer"
        }
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Add session middleware for OAuth state
secret_key = str(settings.SECRET_KEY) if hasattr(settings.SECRET_KEY, "get_secret_value") else settings.SECRET_KEY
app.add_middleware(SessionMiddleware, secret_key=secret_key)

# CORS Configuration
origins = [
    settings.FRONTEND_URL,  # Your deployed frontend
    "http://localhost:3000",  # Local development
    "http://localhost:3001",  # Backup local port
    "https://v0-budget-pay-ui-design.vercel.app",  # Your current deployed frontend
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

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for better error responses"""
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )
    
    # Log the error in production
    print(f"Unhandled exception: {exc}")
    
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

# ------------------------------------------------------------
# AUTHENTICATION ROUTES
# ------------------------------------------------------------

# Custom auth routes (including logout with enhanced authentication)
# Include this BEFORE the default FastAPI Users router to handle the logout endpoint
app.include_router(
    auth.router,
    prefix="/api/v1/auth",
    tags=["Authentication"],
)

# JWT Login
app.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/api/v1/auth/jwt",
    tags=["Authentication"],
)

# Registration
app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/api/v1/auth",
    tags=["Authentication"],
)

# Email verification and password reset routes
app.include_router(
    fastapi_users.get_verify_router(UserRead),
    prefix="/api/v1/auth",
    tags=["Email Verification"],
)

app.include_router(
    fastapi_users.get_reset_password_router(),
    prefix="/api/v1/auth",
    tags=["Password Reset"],
)

# Google OAuth routes
app.include_router(
    google_auth.router,
    prefix="/api/v1/auth/google",
    tags=["Google Authentication"],
)

# REMOVED: Default FastAPI Users router for user management
# app.include_router(
#     fastapi_users.get_users_router(UserRead, UserUpdate),
#     prefix="/api/v1/users",
#     tags=["User Management"],
# )

@app.post("/api/v1/auth/verify-email", tags=["Email Verification"])
async def verify_email_custom(
    token: str = Form(...),
    user_manager: UserManager = Depends(get_user_manager)
):
    """Custom email verification endpoint that accepts token as form data or query param"""
    try:
        # Use FastAPI Users' built-in verification logic
        await user_manager.verify(token)
        return {"message": "Email verified successfully"}
    except Exception as e:
        logger.error(f"Email verification failed: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

# ------------------------------------------------------------
# ROOT ENDPOINT
# ------------------------------------------------------------
@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Budget Pay API is running!",
        "version": "0.1.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "endpoints": {
            "register": "/api/v1/auth/register",
            "login": "/api/v1/auth/jwt/login",
            "logout": "/api/v1/auth/jwt/logout",
            "profile": "/api/v1/users/me",
            "request_verify": "/api/v1/auth/request-verify-token",
            "verify": "/api/v1/auth/verify",
            "forgot_password": "/api/v1/auth/forgot-password",
            "reset_password": "/api/v1/auth/reset-password"
        },
        "features": {
            "email_verification": True,
            "password_reset": True,
            "jwt_authentication": True
        }
    }

# ------------------------------------------------------------
# HEALTH CHECK ENDPOINT
# ------------------------------------------------------------
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    try:
        # You can add database connectivity check here
        return {
            "status": "healthy",
            "timestamp": "2025-06-25T00:00:00Z",
            "version": "1.1.0",
            "environment": settings.ENVIRONMENT
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")

# ------------------------------------------------------------
# BUSINESS LOGIC ROUTES
# ------------------------------------------------------------
# Use our custom users router that uses the enhanced authentication
app.include_router(users.router, prefix="/api/v1/users", tags=["User Management"])
app.include_router(categories.router, prefix="/api/v1")
app.include_router(expenses.router, prefix="/api/v1")
app.include_router(transactions.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(chatbot.router, prefix="/api/v1/chatbot", tags=["Chatbot"])
app.include_router(notification.router, prefix="/api/v1/notification", tags=["notification"])
app.include_router(goals.router, prefix="/api/v1/goals", tags=["goals"])

# ------------------------------------------------------------
# STARTUP EVENT
# ------------------------------------------------------------
@app.on_event("startup")
async def on_startup():
    """Startup event to create database tables"""
    try:
        await create_db_and_tables()
        print("✅ Database tables created successfully")
        print(f"✅ Frontend URL: {settings.FRONTEND_URL}")
        print(f"✅ Backend URL: {settings.BACKEND_BASE_URL}")
        
        # Test SendGrid configuration
        if settings.SENDGRID_API_KEY and settings.EMAIL_FROM:
            print("✅ SendGrid configuration found")
        else:
            print("❌ SendGrid configuration missing")
            
    except Exception as e:
        print(f"❌ Startup error: {str(e)}")
        logging.error(f"Startup error: {str(e)}")

@app.post("/debug/test-email", tags=["Debug"])
async def test_email(email: str):
    """Debug endpoint to test email sending"""
    from app.core.auth import send_email_via_sendgrid
    
    try:
        success = await send_email_via_sendgrid(
            email, 
            "Test Email", 
            "<h1>This is a test email from Budget Pay</h1>"
        )
        return {"success": success, "email": email}
    except Exception as e:
        return {"success": False, "error": str(e), "email": email}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)