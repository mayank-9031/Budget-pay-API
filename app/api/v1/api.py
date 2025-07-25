from fastapi import APIRouter

from app.api.v1.routes import users, categories, transactions, dashboard, chatbot, google_auth, auth, goals, notification

api_router = APIRouter()

api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(categories.router, prefix="/categories", tags=["categories"])
api_router.include_router(transactions.router, prefix="/transactions", tags=["transactions"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(chatbot.router, prefix="/chatbot", tags=["chatbot"])
api_router.include_router(google_auth.router, prefix="/auth/google", tags=["google_auth"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(goals.router, tags=["goals"])
api_router.include_router(notification.router, prefix="/notification", tags=["notifications"])