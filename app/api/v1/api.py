from fastapi import APIRouter

from app.api.v1.routes import users, categories, transactions, dashboard, chatbot

api_router = APIRouter()

api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(categories.router, prefix="/categories", tags=["categories"])
api_router.include_router(transactions.router, prefix="/transactions", tags=["transactions"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(chatbot.router, prefix="/chatbot", tags=["chatbot"])
