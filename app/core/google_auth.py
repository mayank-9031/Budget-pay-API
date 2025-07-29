# app/core/google_auth.py
import json
import uuid
from typing import Dict, Optional, Tuple

import httpx
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request

from app.core.config import settings

# Google OAuth2 endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# Scopes required for the application
SCOPES = [
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
]

def create_oauth_flow(redirect_uri: Optional[str] = None) -> Flow:
    """Create a Google OAuth2 flow instance"""
    client_config = {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": GOOGLE_AUTH_URL,
            "token_uri": GOOGLE_TOKEN_URL,
            "redirect_uris": [redirect_uri or settings.GOOGLE_REDIRECT_URI],
        }
    }
    
    flow = Flow.from_client_config(
        client_config=client_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri or settings.GOOGLE_REDIRECT_URI
    )
    
    return flow

async def get_google_user_info(access_token: str) -> Dict:
    """Get user info from Google using the access token"""
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {access_token}"}
        response = await client.get(GOOGLE_USERINFO_URL, headers=headers)
        response.raise_for_status()
        return response.json()

async def exchange_code_for_token(code: str, redirect_uri: Optional[str] = None) -> Tuple[str, str, Dict]:
    """Exchange authorization code for access token and refresh token"""
    flow = create_oauth_flow(redirect_uri)
    
    # Exchange the authorization code for credentials
    token_info = flow.fetch_token(code=code)
    
    # Get credentials and refresh token
    credentials = flow.credentials
    refresh_token = token_info.get('refresh_token')
    
    # Get user info
    user_info = await get_google_user_info(credentials.token)
    
    return credentials.token, refresh_token, user_info

async def refresh_google_token(refresh_token: str) -> Tuple[str, Optional[str]]:
    """Use refresh token to get a new access token"""
    async with httpx.AsyncClient() as client:
        data = {
            'client_id': settings.GOOGLE_CLIENT_ID,
            'client_secret': settings.GOOGLE_CLIENT_SECRET,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token'
        }
        response = await client.post(GOOGLE_TOKEN_URL, data=data)
        response.raise_for_status()
        token_info = response.json()
        
        return token_info['access_token'], token_info.get('refresh_token') 