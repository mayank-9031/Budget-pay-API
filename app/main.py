# app/main.py
import uvicorn
import os
import logging
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Form, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from app.core.auth import current_active_user, get_user_manager, UserManager
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.core.database import (
    engine, 
    Base, 
    init_db, 
    close_db_connection, 
    check_db_connection, 
    get_pool_status
)
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
    """Create database tables with Supabase compatibility"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Use a fresh connection for table creation
            async with engine.begin() as conn:
                # For Supabase, we need to be more careful about prepared statements
                if settings.is_supabase:
                    # Create tables one by one to avoid prepared statement conflicts
                    def create_tables_sync(sync_conn):
                        # Import all models to ensure they're registered
                        from app.models import user, category, expense, transaction, notification, goal
                        
                        # Create tables with checkfirst=True to avoid conflicts
                        Base.metadata.create_all(sync_conn, checkfirst=True)
                    
                    await conn.run_sync(create_tables_sync)
                else:
                    # Standard table creation for non-Supabase databases
                    await conn.run_sync(Base.metadata.create_all)
            
            logger.info("✅ Database tables created/verified successfully")
            return  # Success, exit function
            
        except Exception as e:
            if "DuplicatePreparedStatementError" in str(e) and attempt < max_retries - 1:
                logger.warning(f"Prepared statement conflict on attempt {attempt + 1}, retrying after cleanup...")
                # Clean up connections and retry
                try:
                    await engine.dispose()
                    import asyncio
                    await asyncio.sleep(1)
                except:
                    pass
                continue
            elif attempt < max_retries - 1:
                logger.warning(f"Table creation failed on attempt {attempt + 1}: {str(e)}, retrying...")
                continue
            else:
                logger.error(f"Table creation failed after all retries: {str(e)}")
                raise

app = FastAPI(
    title="Budget Pay API",
    version="1.1.0",
    openapi_url="/openapi.json",
    openapi_tags=[
        {"name": "Authentication", "description": "Operations related to authentication"},
        {"name": "Google Authentication", "description": "Google OAuth authentication endpoints"},
        {"name": "User Management", "description": "User profile and settings operations"},
        {"name": "Notifications", "description": "Real-time and AI-powered notifications"},
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
    "https://www.budgetpay.in",
    "https://budgetpay.in"
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
    logger.error(f"Unhandled exception: {exc}")
    
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
        "version": "1.1.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "timezone": "Asia/Kolkata",
        "current_time": datetime.now(timezone.utc).isoformat(),
        "endpoints": {
            "register": "/api/v1/auth/register",
            "login": "/api/v1/auth/jwt/login",
            "logout": "/api/v1/auth/jwt/logout",
            "profile": "/api/v1/users/me",
            "notifications": "/api/v1/notification",
            "notification_ws": "/api/v1/notification/ws",
        },
        "features": {
            "email_verification": True,
            "password_reset": True,
            "jwt_authentication": True,
            "real_time_notifications": True,
            "ai_notifications": True,
            "refresh_tokens": True
        }
    }

# ------------------------------------------------------------
# ENHANCED HEALTH CHECK ENDPOINT
# ------------------------------------------------------------
@app.get("/health", tags=["Health"])
async def health_check():
    """Enhanced health check endpoint with database connectivity"""
    try:
        # Check database connectivity
        db_healthy = await check_db_connection()
        pool_status = await get_pool_status() if db_healthy else None
        
        # Get current UTC time
        utc_now = datetime.now(timezone.utc)
        
        # Convert to Indian time (UTC+5:30)
        from datetime import timedelta
        ist_offset = timedelta(hours=5, minutes=30)
        ist_time = (utc_now + ist_offset).strftime("%Y-%m-%d %H:%M:%S IST")
        
        health_data = {
            "status": "healthy" if db_healthy else "unhealthy",
            "timestamp": utc_now.isoformat(),
            "version": "1.1.0",
            "environment": settings.ENVIRONMENT,
            "database": {
                "status": "connected" if db_healthy else "disconnected",
                "pool_status": pool_status
            },
            "timezone": "Asia/Kolkata",
            "local_time_india": ist_time,
            "utc_time": utc_now.strftime("%Y-%m-%d %H:%M:%S UTC")
        }
        
        if not db_healthy:
            return JSONResponse(
                status_code=503,
                content=health_data
            )
            
        return health_data
        
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )

# ------------------------------------------------------------
# TOKEN REFRESH ENDPOINT
# ------------------------------------------------------------
@app.post("/api/v1/auth/refresh", tags=["Authentication"])
async def refresh_token(
    current_user = Depends(current_active_user)
):
    """Refresh access token endpoint"""
    try:
        # For now, return user info to verify token is still valid
        # In a full implementation, you'd generate a new token here
        return {
            "message": "Token is still valid",
            "user_id": str(current_user.id),
            "email": current_user.email,
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # in seconds
            "token_type": "bearer"
        }
    except Exception as e:
        logger.error(f"Token refresh failed: {str(e)}")
        raise HTTPException(status_code=401, detail="Token refresh failed")

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
app.include_router(notification.router, prefix="/api/v1/notification", tags=["Notifications"])
app.include_router(goals.router, prefix="/api/v1/goals", tags=["Goals"])

# ------------------------------------------------------------
# STARTUP EVENT
# ------------------------------------------------------------
@app.on_event("startup")
async def on_startup():
    """Startup event to create database tables and initialize connections"""
    try:
        # Initialize database with health check
        await init_db()
        await create_db_and_tables()
        
        logger.info("✅ Database tables created successfully")
        logger.info(f"✅ Frontend URL: {settings.FRONTEND_URL}")
        logger.info(f"✅ Backend URL: {settings.BACKEND_BASE_URL}")
        logger.info(f"✅ Access token expiry: {settings.ACCESS_TOKEN_EXPIRE_MINUTES} minutes")
        logger.info(f"✅ Refresh token expiry: {settings.REFRESH_TOKEN_EXPIRE_DAYS} days")

        # Test OpenRouter configuration
        if settings.OPENROUTER_API_KEY:
            logger.info("✅ OpenRouter API key configured for AI notifications")
        else:
            logger.info("⚠️ OpenRouter API key not configured - AI notifications will be unavailable")
            
        # Log Google OAuth configuration
        if settings.GOOGLE_CLIENT_ID:
            logger.info("✅ Google OAuth configured")
        else:
            logger.info("⚠️ Google OAuth not configured")
            
    except Exception as e:
        logger.error(f"❌ Startup error: {str(e)}")
        raise

# ------------------------------------------------------------
# SHUTDOWN EVENT
# ------------------------------------------------------------
@app.on_event("shutdown")
async def on_shutdown():
    """Graceful shutdown event"""
    try:
        await close_db_connection()
        logger.info("✅ Application shutdown completed")
    except Exception as e:
        logger.error(f"❌ Shutdown error: {str(e)}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)