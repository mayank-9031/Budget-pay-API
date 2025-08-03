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

async def exchange_code_for_token(code: str, redirect_uri: Optional[str] = None) -> Tuple[str, Dict]:
    """Exchange authorization code for access token"""
    flow = create_oauth_flow(redirect_uri)
    
    # Exchange the authorization code for credentials
    flow.fetch_token(code=code)
    
    # Get credentials
    credentials = flow.credentials
    
    # Get user info
    user_info = await get_google_user_info(credentials.token)
    
    return credentials.token, user_info

async def exchange_mobile_auth_code(code: str) -> Tuple[str, Dict]:
    """Exchange server auth code from mobile app for tokens"""
    try:
        # For mobile apps, we use a special redirect_uri value
        token_url = "https://oauth2.googleapis.com/token"
        
        # Prepare the request data
        data = {
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": "postmessage",  # Special value for mobile apps
            "grant_type": "authorization_code"
        }
        
        # Make the token request
        async with httpx.AsyncClient() as client:
            response = await client.post(token_url, data=data)
            response.raise_for_status()
            token_data = response.json()
        
        # Extract tokens
        access_token = token_data.get("access_token")
        id_token = token_data.get("id_token")
        
        if not access_token:
            raise ValueError("No access token received from Google")
        
        # Get user info using the access token
        user_info = await get_google_user_info(access_token)
        
        return access_token, user_info
        
    except httpx.HTTPError as e:
        raise ValueError(f"HTTP error during token exchange: {str(e)}")
    except Exception as e:
        raise ValueError(f"Error exchanging mobile auth code: {str(e)}") 