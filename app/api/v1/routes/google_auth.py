# app/api/v1/routes/google_auth.py
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status, Security
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import User, get_user_manager, UserManager, create_access_token, current_active_user
from app.core.database import get_async_session
from app.core.google_auth import create_oauth_flow, exchange_code_for_token
from app.schemas.user import GoogleAuthRequest, GoogleAuthResponse, GoogleCallbackRequest, Token, UserProfile
from app.core.config import settings

router = APIRouter()

# Define security scheme
security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)

@router.post("/login", response_model=GoogleAuthResponse)
async def google_login(
    request: GoogleAuthRequest,
    request_obj: Request
):
    """
    Initiate Google OAuth login flow
    """
    try:
        # Create OAuth flow
        flow = create_oauth_flow(request.redirect_uri)
        
        # Generate authorization URL with state
        auth_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        
        # Store state in session for verification during callback
        request_obj.session["oauth_state"] = state
        
        return {"authorization_url": auth_url}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate Google login: {str(e)}"
        )

@router.get("/callback")
async def google_callback(
    request: Request,
    code: str,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: AsyncSession = Depends(get_async_session),
    user_manager: UserManager = Depends(get_user_manager)
):
    """
    Handle Google OAuth callback
    """
    # Check for errors
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google OAuth error: {error}"
        )
    
    try:
        # Exchange code for token
        access_token, user_info = await exchange_code_for_token(code)
        
        # Get user email from Google profile
        email = user_info.get("email")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email not provided by Google"
            )
        
        # Check if user exists
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalars().first()
        
        # If user doesn't exist, create a new one
        if not user:
            # Create user with Google info
            new_user = User(
                email=email,
                hashed_password="",  # No password for Google users
                is_active=True,
                is_verified=True,  # Google already verified the email
                full_name=user_info.get("name"),
                google_id=user_info.get("sub"),
                google_access_token=access_token,
                google_token_expiry=datetime.utcnow() + timedelta(hours=1)
            )
            db.add(new_user)
            await db.commit()
            await db.refresh(new_user)
            user = new_user
        else:
            # Update existing user with Google info
            await db.execute(
                update(User)
                .where(User.id == user.id)
                .values(
                    google_id=user_info.get("sub"),
                    google_access_token=access_token,
                    google_token_expiry=datetime.utcnow() + timedelta(hours=1),
                    full_name=user_info.get("name") if user_info.get("name") else user.full_name
                )
            )
            await db.commit()
            await db.refresh(user)
        
        # Generate JWT token
        token = create_access_token(str(user.id))
        
        # Log the token for debugging
        print(f"Generated token: {token[:10]}...")
        
        # Construct redirect URL with token
        # Use a more explicit token parameter and include additional user info
        redirect_url = f"{settings.FRONTEND_URL}/auth/google-callback?access_token={token}&token_type=bearer&user_id={user.id}&email={email}"
        
        # Log the successful authentication
        print(f"Google OAuth successful for user: {email}. Redirecting to: {redirect_url}")
        
        # Set token in cookies as a backup method
        response = RedirectResponse(url=redirect_url)
        response.set_cookie(
            key="access_token",
            value=f"Bearer {token}",
            httponly=True,
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            samesite="lax"
        )
        
        return response
    except Exception as e:
        # Log the error for debugging
        print(f"Google OAuth error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process Google callback: {str(e)}"
        )

@router.get("/verify-token", summary="Verify authentication token", description="Requires a valid JWT token in the Authorization header")
async def verify_token(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    credentials: HTTPAuthorizationCredentials = Security(optional_security)
) -> Dict[str, Any]:
    """
    Verify that the token is valid and return user information.
    This endpoint can be used by the frontend to check if the user is authenticated.
    
    **Important**: You must include a valid JWT token in the Authorization header.
    Format: `Authorization: Bearer YOUR_TOKEN_HERE`
    """
    import jwt
    from datetime import datetime
    
    # Try to get token from various sources
    auth_header = request.headers.get("Authorization", "")
    token = None
    
    # From Authorization header
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]  # Remove "Bearer " prefix
    elif credentials and credentials.credentials:
        token = credentials.credentials
    
    # From query parameter
    if not token:
        token = request.query_params.get("token") or request.query_params.get("access_token")
    
    # From cookie
    if not token:
        token = request.cookies.get("access_token")
        # Remove "Bearer " prefix if present in cookie
        if token and token.startswith("Bearer "):
            token = token[7:]
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        # Convert SecretStr to str if needed
        secret_key = str(settings.SECRET_KEY) if hasattr(settings.SECRET_KEY, "get_secret_value") else settings.SECRET_KEY
        
        # Decode the token
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[settings.ALGORITHM]
        )
        
        # Check if token is expired
        if datetime.utcnow().timestamp() > payload.get("exp", 0):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Get user ID from token
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Get user from database
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Return user info
        return {
            "authenticated": True,
            "user_id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication error: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

@router.get("/debug-auth")
async def debug_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(optional_security)
):
    """
    Debug endpoint to check what authentication information is being received
    """
    auth_header = request.headers.get("Authorization", "")
    cookies = request.cookies
    
    # Check for token in various places
    token_in_header = auth_header if auth_header.startswith("Bearer ") else None
    token_in_cookie = cookies.get("access_token")
    
    # Get token from security if available
    token_from_security = credentials.credentials if credentials else None
    
    return {
        "auth_header": auth_header,
        "token_in_header": bool(token_in_header),
        "token_in_cookie": bool(token_in_cookie),
        "token_from_security": bool(token_from_security),
        "cookies": {k: "..." for k in cookies.keys()},
        "headers": {k: v for k, v in request.headers.items()},
    } 

@router.get("/auth-with-token")
async def auth_with_token(token: str, db: AsyncSession = Depends(get_async_session)):
    """
    Alternative authentication endpoint that accepts token as a query parameter
    """
    try:
        import jwt
        from datetime import datetime
        
        # Decode the token
        payload = jwt.decode(
            token,
            str(settings.SECRET_KEY) if hasattr(settings.SECRET_KEY, "get_secret_value") else settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        
        # Check if token is expired
        if datetime.utcnow().timestamp() > payload.get("exp", 0):
            return {"authenticated": False, "error": "Token has expired"}
        
        # Get user ID from token
        user_id = payload.get("sub")
        if not user_id:
            return {"authenticated": False, "error": "Invalid token: missing user ID"}
        
        # Get user from database
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        
        if not user:
            return {"authenticated": False, "error": "User not found"}
        
        # Return user info
        return {
            "authenticated": True,
            "user_id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
        }
    except Exception as e:
        return {"authenticated": False, "error": str(e)} 

@router.get("/test-page", response_class=HTMLResponse)
async def test_page():
    """
    Serves a simple HTML page for testing the authentication flow
    """
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Google OAuth Test</title>
        <script>
            // Function to extract URL parameters
            function getUrlParams() {
                const params = {};
                const queryString = window.location.search.substring(1);
                const pairs = queryString.split('&');
                
                for (const pair of pairs) {
                    const [key, value] = pair.split('=');
                    if (key) {
                        params[decodeURIComponent(key)] = decodeURIComponent(value || '');
                    }
                }
                
                return params;
            }
            
            // Function to check authentication status
            async function checkAuth() {
                const token = localStorage.getItem('access_token');
                if (!token) {
                    document.getElementById('status').textContent = 'Not authenticated';
                    return;
                }
                
                try {
                    const response = await fetch('/api/v1/auth/google/debug-auth', {
                        headers: {
                            'Authorization': `Bearer ${token}`
                        }
                    });
                    
                    const data = await response.json();
                    document.getElementById('debug').textContent = JSON.stringify(data, null, 2);
                    
                    // Try to get user info
                    const userResponse = await fetch('/api/v1/auth/google/auth-with-token?token=' + token);
                    const userData = await userResponse.json();
                    
                    if (userData.authenticated) {
                        document.getElementById('status').textContent = `Authenticated as: ${userData.email}`;
                        document.getElementById('user-info').textContent = JSON.stringify(userData, null, 2);
                    } else {
                        document.getElementById('status').textContent = 'Authentication failed: ' + userData.error;
                    }
                } catch (error) {
                    document.getElementById('status').textContent = 'Error checking auth: ' + error.message;
                }
            }
            
            // When the page loads
            window.onload = function() {
                // Check for token in URL
                const params = getUrlParams();
                if (params.access_token) {
                    localStorage.setItem('access_token', params.access_token);
                    document.getElementById('token').value = params.access_token;
                    document.getElementById('token-display').textContent = params.access_token;
                    
                    // Remove token from URL (for security)
                    const cleanUrl = window.location.protocol + '//' + window.location.host + window.location.pathname;
                    window.history.replaceState({}, document.title, cleanUrl);
                } else {
                    // Check if we have a token in localStorage
                    const token = localStorage.getItem('access_token');
                    if (token) {
                        document.getElementById('token').value = token;
                        document.getElementById('token-display').textContent = token;
                    }
                }
                
                // Check auth status
                checkAuth();
            };
            
            // Function to initiate Google login
            async function loginWithGoogle() {
                try {
                    const response = await fetch('/api/v1/auth/google/login', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({})
                    });
                    
                    const data = await response.json();
                    if (data.authorization_url) {
                        window.location.href = data.authorization_url;
                    } else {
                        document.getElementById('status').textContent = 'Failed to get authorization URL';
                    }
                } catch (error) {
                    document.getElementById('status').textContent = 'Error initiating login: ' + error.message;
                }
            }
            
            // Function to manually set token
            function setToken() {
                const token = document.getElementById('token').value;
                localStorage.setItem('access_token', token);
                document.getElementById('token-display').textContent = token;
                checkAuth();
            }
            
            // Function to clear token
            function clearToken() {
                localStorage.removeItem('access_token');
                document.getElementById('token').value = '';
                document.getElementById('token-display').textContent = '';
                document.getElementById('status').textContent = 'Token cleared';
                document.getElementById('user-info').textContent = '';
                document.getElementById('debug').textContent = '';
            }
        </script>
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 20px;
                line-height: 1.6;
            }
            .container {
                max-width: 800px;
                margin: 0 auto;
            }
            .card {
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 20px;
                margin-bottom: 20px;
            }
            button {
                background-color: #4285F4;
                color: white;
                border: none;
                padding: 10px 15px;
                border-radius: 4px;
                cursor: pointer;
                margin-right: 10px;
            }
            input {
                padding: 8px;
                width: 300px;
                margin-right: 10px;
            }
            pre {
                background-color: #f5f5f5;
                padding: 10px;
                border-radius: 4px;
                overflow-x: auto;
            }
            .token-display {
                word-break: break-all;
                background-color: #f5f5f5;
                padding: 10px;
                border-radius: 4px;
                margin-top: 10px;
                font-family: monospace;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Google OAuth Test Page</h1>
            
            <div class="card">
                <h2>Authentication</h2>
                <button onclick="loginWithGoogle()">Login with Google</button>
                <p id="status">Checking authentication status...</p>
            </div>
            
            <div class="card">
                <h2>Token Management</h2>
                <div>
                    <input type="text" id="token" placeholder="Enter token manually">
                    <button onclick="setToken()">Set Token</button>
                    <button onclick="clearToken()">Clear Token</button>
                </div>
                <h3>Current Token:</h3>
                <div id="token-display" class="token-display"></div>
            </div>
            
            <div class="card">
                <h2>User Info</h2>
                <pre id="user-info"></pre>
            </div>
            
            <div class="card">
                <h2>Debug Info</h2>
                <pre id="debug"></pre>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content) 

@router.get("/generate-test-token/{user_id}")
async def generate_test_token(
    user_id: str,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Generate a test token for a user by ID.
    This is for debugging purposes only and should be disabled in production.
    """
    try:
        # Try to find the user
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        
        if not user:
            return {"error": "User not found"}
        
        # Generate token
        token = create_access_token(str(user.id))
        
        # Return token and instructions
        return {
            "user_id": str(user.id),
            "email": user.email,
            "token": token,
            "instructions": "Use this token in the Authorization header as 'Bearer {token}'",
            "curl_example": f"curl -H 'Authorization: Bearer {token}' http://localhost:8000/api/v1/auth/google/verify-token",
            "fetch_example": f"fetch('/api/v1/auth/google/verify-token', {{ headers: {{ Authorization: 'Bearer {token}' }} }})"
        }
    except Exception as e:
        return {"error": str(e)} 

@router.get("/list-users")
async def list_users(db: AsyncSession = Depends(get_async_session)):
    """
    List all users in the database.
    This is for debugging purposes only and should be disabled in production.
    """
    try:
        # Get all users
        result = await db.execute(select(User))
        users = result.scalars().all()
        
        # Return user list
        return {
            "users": [
                {
                    "id": str(user.id),
                    "email": user.email,
                    "full_name": user.full_name,
                    "is_active": user.is_active,
                    "is_verified": user.is_verified,
                    "has_google": bool(user.google_id)
                }
                for user in users
            ]
        }
    except Exception as e:
        return {"error": str(e)} 

@router.get("/simple-verify", summary="Simple token verification", description="A simpler endpoint to verify authentication")
async def simple_verify(
    request: Request,
    db: AsyncSession = Depends(get_async_session)
):
    """
    A simpler endpoint to verify authentication.
    Accepts token from Authorization header, query parameter, or cookie.
    """
    import jwt
    from datetime import datetime
    
    # Try to get token from various sources
    auth_header = request.headers.get("Authorization", "")
    token = None
    
    # From Authorization header
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]  # Remove "Bearer " prefix
    
    # From query parameter
    if not token:
        token = request.query_params.get("token")
    
    # From cookie
    if not token:
        token = request.cookies.get("access_token")
        # Remove "Bearer " prefix if present in cookie
        if token and token.startswith("Bearer "):
            token = token[7:]
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    try:
        # Convert SecretStr to str if needed
        secret_key = str(settings.SECRET_KEY) if hasattr(settings.SECRET_KEY, "get_secret_value") else settings.SECRET_KEY
        
        # Decode the token
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[settings.ALGORITHM]
        )
        
        # Get user ID from token
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Get user from database
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        # Return user info
        return {
            "authenticated": True,
            "user_id": str(user.id),
            "email": user.email
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e)) 

@router.get("/docs", response_class=HTMLResponse, include_in_schema=False)
async def frontend_docs():
    """
    Documentation for frontend developers on how to integrate Google OAuth.
    """
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Google OAuth Integration Guide</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                line-height: 1.6;
                max-width: 900px;
                margin: 0 auto;
                padding: 20px;
            }
            pre {
                background-color: #f5f5f5;
                padding: 10px;
                border-radius: 5px;
                overflow-x: auto;
            }
            code {
                background-color: #f5f5f5;
                padding: 2px 4px;
                border-radius: 3px;
            }
            .endpoint {
                background-color: #e8f4f8;
                padding: 15px;
                border-radius: 5px;
                margin-bottom: 20px;
            }
            h3 {
                margin-top: 30px;
            }
            table {
                border-collapse: collapse;
                width: 100%;
            }
            th, td {
                border: 1px solid #ddd;
                padding: 8px;
                text-align: left;
            }
            th {
                background-color: #f2f2f2;
            }
        </style>
    </head>
    <body>
        <h1>Google OAuth Integration Guide</h1>
        
        <h2>Endpoints Overview</h2>
        
        <div class="endpoint">
            <h3>1. Initiate Google Login</h3>
            <p><strong>URL:</strong> <code>/api/v1/auth/google/login</code></p>
            <p><strong>Method:</strong> POST</p>
            <p><strong>Request Body:</strong> <code>{}</code></p>
            <p><strong>Response:</strong> <code>{ "authorization_url": "https://accounts.google.com/..." }</code></p>
            <p><strong>Description:</strong> Returns a Google authorization URL that the user should be redirected to</p>
            
            <pre>// Example usage
fetch('/api/v1/auth/google/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({})
})
.then(response => response.json())
.then(data => {
  // Redirect to Google's consent page
  window.location.href = data.authorization_url;
});</pre>
        </div>
        
        <div class="endpoint">
            <h3>2. Google OAuth Callback</h3>
            <p><strong>URL:</strong> <code>/api/v1/auth/google/callback</code> (handled by backend)</p>
            <p><strong>Method:</strong> GET</p>
            <p><strong>Description:</strong> Backend handles the OAuth callback and redirects to frontend</p>
            <p><strong>Redirect URL:</strong> <code>{FRONTEND_URL}/auth/google-callback?access_token={token}&token_type=bearer&user_id={id}&email={email}</code></p>
            
            <pre>// Example callback handler component
useEffect(() => {
  // Extract token from URL
  const urlParams = new URLSearchParams(window.location.search);
  const token = urlParams.get('access_token');
  
  if (token) {
    // Store the token
    localStorage.setItem('access_token', token);
    
    // Redirect to dashboard
    navigate('/dashboard');
  }
}, []);</pre>
        </div>
        
        <div class="endpoint">
            <h3>3. Verify Authentication</h3>
            <p><strong>URL:</strong> <code>/api/v1/auth/google/verify-token</code></p>
            <p><strong>Method:</strong> GET</p>
            <p><strong>Headers:</strong> <code>Authorization: Bearer {token}</code></p>
            <p><strong>Response:</strong> User profile information if authenticated</p>
            
            <pre>// Example usage
const token = localStorage.getItem('access_token');

fetch('/api/v1/auth/google/verify-token', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
})
.then(response => {
  if (response.ok) {
    return response.json();
  }
  throw new Error('Authentication failed');
})
.then(userData => {
  console.log('Authenticated as:', userData.email);
});</pre>
        </div>
        
        <div class="endpoint">
            <h3>4. User Profile</h3>
            <p><strong>URL:</strong> <code>/api/v1/users/me</code></p>
            <p><strong>Method:</strong> GET</p>
            <p><strong>Headers:</strong> <code>Authorization: Bearer {token}</code></p>
            <p><strong>Response:</strong> User profile information</p>
            
            <pre>// Example usage
const token = localStorage.getItem('access_token');

fetch('/api/v1/users/me', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
})
.then(response => response.json())
.then(profile => {
  console.log('User profile:', profile);
});</pre>
        </div>
        
        <h2>Authentication Flow</h2>
        
        <ol>
            <li>
                <strong>User clicks "Sign in with Google" button</strong>
                <ul>
                    <li>Frontend sends a POST request to <code>/api/v1/auth/google/login</code></li>
                    <li>Backend returns an authorization URL</li>
                    <li>Frontend redirects the user to this URL</li>
                </ul>
            </li>
            <li>
                <strong>User authorizes the application on Google's page</strong>
                <ul>
                    <li>Google redirects back to the backend's callback URL</li>
                    <li>Backend processes the callback and creates/updates the user</li>
                    <li>Backend redirects to frontend with the token</li>
                </ul>
            </li>
            <li>
                <strong>Frontend receives the token</strong>
                <ul>
                    <li>Frontend extracts the token from the URL</li>
                    <li>Frontend stores the token (e.g., in localStorage)</li>
                    <li>Frontend uses this token for subsequent API calls</li>
                </ul>
            </li>
            <li>
                <strong>Frontend uses token for authenticated requests</strong>
                <ul>
                    <li>Include the token in the Authorization header for all API requests</li>
                    <li>Format: <code>Authorization: Bearer {token}</code></li>
                </ul>
            </li>
        </ol>
        
        <h2>Important Notes</h2>
        
        <ul>
            <li><strong>Token Expiration:</strong> Tokens are valid for 7 days (10080 minutes)</li>
            <li><strong>Error Handling:</strong> Implement proper error handling for authentication failures</li>
            <li><strong>Security Best Practices:</strong>
                <ul>
                    <li>Remove tokens from the URL after extracting them</li>
                    <li>Store tokens securely</li>
                    <li>Implement proper logout functionality</li>
                </ul>
            </li>
            <li><strong>Testing:</strong> Use the test page at <code>/api/v1/auth/google/test-page</code> during development</li>
            <li><strong>Debugging:</strong> If authentication issues occur, use <code>/api/v1/auth/google/debug-auth</code> to debug</li>
        </ul>
        
        <h2>Common Issues</h2>
        
        <table>
            <tr>
                <th>Issue</th>
                <th>Possible Cause</th>
                <th>Solution</th>
            </tr>
            <tr>
                <td>401 Unauthorized</td>
                <td>Missing or invalid token</td>
                <td>Check that the token is being sent correctly in the Authorization header</td>
            </tr>
            <tr>
                <td>Token not being stored</td>
                <td>Issue with localStorage or callback handling</td>
                <td>Check browser console for errors and verify that the token is being extracted correctly from the URL</td>
            </tr>
            <tr>
                <td>Token expiration</td>
                <td>Token has expired</td>
                <td>Implement token refresh or redirect to login</td>
            </tr>
            <tr>
                <td>CORS issues</td>
                <td>Backend CORS configuration</td>
                <td>Check that the frontend domain is allowed in the CORS configuration</td>
            </tr>
        </table>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content) 

@router.get("/raw-token-test")
async def raw_token_test(request: Request):
    """
    A raw token test endpoint that doesn't use any security dependencies.
    This endpoint simply returns the Authorization header value.
    """
    auth_header = request.headers.get("Authorization", "")
    
    # Try to extract the token from the Authorization header
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]  # Remove "Bearer " prefix
    
    # Check for token in query parameters
    token_param = request.query_params.get("token")
    
    # Check for token in cookies
    token_cookie = request.cookies.get("access_token")
    
    return {
        "received_auth_header": auth_header,
        "extracted_token": token,
        "token_from_query": token_param,
        "token_from_cookie": token_cookie,
        "all_headers": dict(request.headers),
        "all_cookies": request.cookies,
        "instructions": "To use this endpoint, include 'Authorization: Bearer YOUR_TOKEN' in the request headers"
    } 

@router.get("/manual-verify")
async def manual_verify(request: Request, db: AsyncSession = Depends(get_async_session)):
    """
    Manually verify a token from any source (header, query param, or cookie).
    This endpoint doesn't use any security dependencies.
    """
    import jwt
    from datetime import datetime
    
    # Try to get token from various sources
    auth_header = request.headers.get("Authorization", "")
    token = None
    
    # From Authorization header
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]  # Remove "Bearer " prefix
    
    # From query parameter
    if not token:
        token = request.query_params.get("token")
    
    # From cookie
    if not token:
        token = request.cookies.get("access_token")
        # Remove "Bearer " prefix if present in cookie
        if token and token.startswith("Bearer "):
            token = token[7:]
    
    if not token:
        return {
            "authenticated": False,
            "error": "No token found in Authorization header, query parameter, or cookie",
            "help": "Try accessing this endpoint with ?token=YOUR_TOKEN or with Authorization: Bearer YOUR_TOKEN header"
        }
    
    try:
        # Convert SecretStr to str if needed
        secret_key = str(settings.SECRET_KEY) if hasattr(settings.SECRET_KEY, "get_secret_value") else settings.SECRET_KEY
        
        # Decode the token
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[settings.ALGORITHM]
        )
        
        # Check if token is expired
        if datetime.utcnow().timestamp() > payload.get("exp", 0):
            return {
                "authenticated": False,
                "error": "Token has expired",
                "payload": payload,
                "current_time": datetime.utcnow().timestamp(),
                "expiry_time": payload.get("exp")
            }
        
        # Get user ID from token
        user_id = payload.get("sub")
        if not user_id:
            return {
                "authenticated": False,
                "error": "Invalid token: missing user ID",
                "payload": payload
            }
        
        # Get user from database
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        
        if not user:
            return {
                "authenticated": False,
                "error": "User not found",
                "user_id": user_id
            }
        
        # Return user info
        return {
            "authenticated": True,
            "user_id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "token_payload": payload
        }
    except Exception as e:
        return {
            "authenticated": False,
            "error": str(e),
            "token_first_chars": token[:10] + "..." if token else None
        } 

@router.get("/token-test", response_class=HTMLResponse)
async def token_test():
    """
    A comprehensive HTML page for testing token authentication with detailed diagnostics.
    """
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Token Authentication Tester</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                line-height: 1.6;
                max-width: 900px;
                margin: 0 auto;
                padding: 20px;
            }
            .card {
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 20px;
                margin-bottom: 20px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            pre {
                background-color: #f5f5f5;
                padding: 10px;
                border-radius: 5px;
                overflow-x: auto;
            }
            code {
                background-color: #f5f5f5;
                padding: 2px 4px;
                border-radius: 3px;
                font-family: monospace;
            }
            input, textarea {
                padding: 8px;
                width: 100%;
                margin-bottom: 10px;
                box-sizing: border-box;
                font-family: monospace;
            }
            button {
                background-color: #4285F4;
                color: white;
                border: none;
                padding: 10px 15px;
                border-radius: 4px;
                cursor: pointer;
                margin-right: 10px;
                margin-bottom: 10px;
            }
            .success {
                color: #28a745;
                font-weight: bold;
            }
            .error {
                color: #dc3545;
                font-weight: bold;
            }
            .endpoint {
                background-color: #e8f4f8;
                padding: 10px;
                border-radius: 5px;
                margin-bottom: 10px;
                font-family: monospace;
            }
            .tab {
                overflow: hidden;
                border: 1px solid #ccc;
                background-color: #f1f1f1;
                border-radius: 5px 5px 0 0;
            }
            .tab button {
                background-color: inherit;
                float: left;
                border: none;
                outline: none;
                cursor: pointer;
                padding: 10px 16px;
                transition: 0.3s;
                color: #333;
                margin: 0;
            }
            .tab button:hover {
                background-color: #ddd;
            }
            .tab button.active {
                background-color: #4285F4;
                color: white;
            }
            .tabcontent {
                display: none;
                padding: 20px;
                border: 1px solid #ccc;
                border-top: none;
                border-radius: 0 0 5px 5px;
            }
            .token-display {
                word-break: break-all;
                background-color: #f8f9fa;
                padding: 10px;
                border-radius: 4px;
                font-family: monospace;
                border: 1px solid #ddd;
            }
            .jwt-part {
                padding: 5px;
                margin-bottom: 5px;
                border-radius: 3px;
            }
            .jwt-header {
                background-color: #e9f5ff;
            }
            .jwt-payload {
                background-color: #f0fff4;
            }
            .jwt-signature {
                background-color: #fff5f5;
            }
            table {
                width: 100%;
                border-collapse: collapse;
            }
            th, td {
                padding: 8px;
                text-align: left;
                border-bottom: 1px solid #ddd;
            }
            th {
                background-color: #f2f2f2;
            }
        </style>
    </head>
    <body>
        <h1>Token Authentication Diagnostic Tool</h1>
        
        <div class="card">
            <h2>Token Input</h2>
            <p>Enter your JWT token below:</p>
            <textarea id="token" rows="3" placeholder="Enter your JWT token"></textarea>
            <button onclick="analyzeToken()">Analyze Token</button>
            <button onclick="loadFromLocalStorage()">Load from localStorage</button>
            <button onclick="loadFromCookie()">Load from Cookie</button>
            <button onclick="clearToken()">Clear</button>
        </div>
        
        <div class="tab">
            <button class="tablinks active" onclick="openTab(event, 'TokenInfo')">Token Info</button>
            <button class="tablinks" onclick="openTab(event, 'TestEndpoints')">Test Endpoints</button>
            <button class="tablinks" onclick="openTab(event, 'Troubleshooting')">Troubleshooting</button>
        </div>
        
        <div id="TokenInfo" class="tabcontent" style="display: block;">
            <h2>Token Analysis</h2>
            <div id="tokenInfo">
                <p>Enter a token and click "Analyze Token" to see details.</p>
            </div>
        </div>
        
        <div id="TestEndpoints" class="tabcontent">
            <h2>Test Endpoints</h2>
            <p>Test your token against different authentication endpoints:</p>
            
            <div class="endpoint">
                <code>GET /api/v1/auth/google/verify-token</code>
                <button onclick="testEndpoint('verify-token')">Test</button>
            </div>
            
            <div class="endpoint">
                <code>GET /api/v1/auth/google/simple-verify</code>
                <button onclick="testEndpoint('simple-verify')">Test</button>
            </div>
            
            <div class="endpoint">
                <code>GET /api/v1/auth/google/manual-verify</code>
                <button onclick="testEndpoint('manual-verify')">Test</button>
            </div>
            
            <div class="endpoint">
                <code>GET /api/v1/auth/google/debug-auth</code>
                <button onclick="testEndpoint('debug-auth')">Test</button>
            </div>
            
            <div class="endpoint">
                <code>GET /api/v1/auth/google/raw-token-test</code>
                <button onclick="testEndpoint('raw-token-test')">Test</button>
            </div>
            
            <div class="endpoint">
                <code>GET /api/v1/users/me</code>
                <button onclick="testEndpoint('users-me')">Test</button>
            </div>
            
            <h3>Results:</h3>
            <pre id="endpointResults">Results will appear here</pre>
        </div>
        
        <div id="Troubleshooting" class="tabcontent">
            <h2>Troubleshooting Guide</h2>
            
            <div class="card">
                <h3>Common Issues</h3>
                <table>
                    <tr>
                        <th>Issue</th>
                        <th>Possible Cause</th>
                        <th>Solution</th>
                    </tr>
                    <tr>
                        <td>401 Unauthorized</td>
                        <td>Missing or invalid token</td>
                        <td>Check that the token is being sent correctly in the Authorization header</td>
                    </tr>
                    <tr>
                        <td>Token not being sent</td>
                        <td>Header format issue</td>
                        <td>Ensure the token is sent as <code>Authorization: Bearer YOUR_TOKEN</code></td>
                    </tr>
                    <tr>
                        <td>Token has expired</td>
                        <td>Token expiration time has passed</td>
                        <td>Generate a new token or extend token lifetime</td>
                    </tr>
                    <tr>
                        <td>CORS issues</td>
                        <td>Browser security restrictions</td>
                        <td>Check that your domain is allowed in the backend CORS configuration</td>
                    </tr>
                </table>
            </div>
            
            <div class="card">
                <h3>Debug Tools</h3>
                <button onclick="checkCORSConfig()">Check CORS Configuration</button>
                <button onclick="checkBrowserStorage()">Check Browser Storage</button>
                <button onclick="generateTestRequest()">Generate Test Request</button>
                
                <div id="debugOutput" style="margin-top: 20px;">
                    <p>Debug output will appear here</p>
                </div>
            </div>
        </div>
        
        <script>
            // Function to analyze JWT token
            function analyzeToken() {
                const tokenInput = document.getElementById('token').value.trim();
                let token = tokenInput;
                
                // Remove "Bearer " prefix if present
                if (token.startsWith('Bearer ')) {
                    token = token.substring(7);
                }
                
                if (!token) {
                    document.getElementById('tokenInfo').innerHTML = '<p class="error">Please enter a token</p>';
                    return;
                }
                
                try {
                    // Split the token into parts
                    const parts = token.split('.');
                    if (parts.length !== 3) {
                        document.getElementById('tokenInfo').innerHTML = '<p class="error">Invalid JWT token format. Expected 3 parts separated by dots.</p>';
                        return;
                    }
                    
                    // Decode header and payload
                    const header = JSON.parse(atob(parts[0]));
                    const payload = JSON.parse(atob(parts[1]));
                    
                    // Format expiration time
                    let expiryInfo = '';
                    if (payload.exp) {
                        const expiryDate = new Date(payload.exp * 1000);
                        const now = new Date();
                        const isExpired = now > expiryDate;
                        
                        expiryInfo = `
                            <p><strong>Expiration:</strong> ${expiryDate.toLocaleString()}</p>
                            <p><strong>Status:</strong> <span class="${isExpired ? 'error' : 'success'}">${isExpired ? 'EXPIRED' : 'VALID'}</span></p>
                            <p><strong>Current time:</strong> ${now.toLocaleString()}</p>
                        `;
                    }
                    
                    // Calculate time left
                    let timeLeftInfo = '';
                    if (payload.exp) {
                        const expiryTime = payload.exp * 1000;
                        const now = Date.now();
                        const timeLeft = expiryTime - now;
                        
                        if (timeLeft > 0) {
                            const hours = Math.floor(timeLeft / (1000 * 60 * 60));
                            const minutes = Math.floor((timeLeft % (1000 * 60 * 60)) / (1000 * 60));
                            timeLeftInfo = `<p><strong>Time left:</strong> ${hours} hours, ${minutes} minutes</p>`;
                        } else {
                            timeLeftInfo = `<p><strong>Time left:</strong> <span class="error">Expired</span></p>`;
                        }
                    }
                    
                    // Build the HTML output
                    const html = `
                        <h3>Token Overview</h3>
                        <div class="token-display">${token}</div>
                        
                        <h3>Token Parts</h3>
                        <div class="jwt-part jwt-header">
                            <h4>Header</h4>
                            <pre>${JSON.stringify(header, null, 2)}</pre>
                        </div>
                        
                        <div class="jwt-part jwt-payload">
                            <h4>Payload</h4>
                            <pre>${JSON.stringify(payload, null, 2)}</pre>
                        </div>
                        
                        <div class="jwt-part jwt-signature">
                            <h4>Signature</h4>
                            <code>${parts[2]}</code>
                        </div>
                        
                        <h3>Token Information</h3>
                        <p><strong>Algorithm:</strong> ${header.alg}</p>
                        <p><strong>Type:</strong> ${header.typ}</p>
                        <p><strong>Subject (User ID):</strong> ${payload.sub || 'Not specified'}</p>
                        <p><strong>Issued at:</strong> ${payload.iat ? new Date(payload.iat * 1000).toLocaleString() : 'Not specified'}</p>
                        ${expiryInfo}
                        ${timeLeftInfo}
                    `;
                    
                    document.getElementById('tokenInfo').innerHTML = html;
                } catch (error) {
                    document.getElementById('tokenInfo').innerHTML = `<p class="error">Error analyzing token: ${error.message}</p>`;
                }
            }
            
            // Function to test an endpoint
            async function testEndpoint(endpoint) {
                const token = document.getElementById('token').value.trim();
                let cleanToken = token;
                
                // Remove "Bearer " prefix if present
                if (cleanToken.startsWith('Bearer ')) {
                    cleanToken = cleanToken.substring(7);
                }
                
                if (!cleanToken) {
                    document.getElementById('endpointResults').textContent = 'Please enter a token first';
                    return;
                }
                
                try {
                    let url;
                    if (endpoint === 'users-me') {
                        url = '/api/v1/users/me';
                    } else {
                        url = `/api/v1/auth/google/${endpoint}`;
                    }
                    
                    const response = await fetch(url, {
                        headers: {
                            'Authorization': `Bearer ${cleanToken}`
                        }
                    });
                    
                    const data = await response.json();
                    
                    document.getElementById('endpointResults').textContent = JSON.stringify({
                        endpoint: url,
                        status: response.status,
                        statusText: response.statusText,
                        ok: response.ok,
                        data: data
                    }, null, 2);
                } catch (error) {
                    document.getElementById('endpointResults').textContent = JSON.stringify({
                        endpoint: endpoint,
                        error: error.message
                    }, null, 2);
                }
            }
            
            // Function to load token from localStorage
            function loadFromLocalStorage() {
                const token = localStorage.getItem('access_token');
                if (token) {
                    document.getElementById('token').value = token;
                    analyzeToken();
                } else {
                    document.getElementById('tokenInfo').innerHTML = '<p class="error">No token found in localStorage</p>';
                }
            }
            
            // Function to load token from cookie
            function loadFromCookie() {
                const cookies = document.cookie.split(';');
                let token = null;
                
                for (const cookie of cookies) {
                    const [name, value] = cookie.trim().split('=');
                    if (name === 'access_token') {
                        token = value;
                        break;
                    }
                }
                
                if (token) {
                    // Remove "Bearer " prefix if present
                    if (token.startsWith('Bearer%20')) {
                        token = token.substring(9);
                    }
                    document.getElementById('token').value = decodeURIComponent(token);
                    analyzeToken();
                } else {
                    document.getElementById('tokenInfo').innerHTML = '<p class="error">No token found in cookies</p>';
                }
            }
            
            // Function to clear token
            function clearToken() {
                document.getElementById('token').value = '';
                document.getElementById('tokenInfo').innerHTML = '<p>Enter a token and click "Analyze Token" to see details.</p>';
            }
            
            // Tab functionality
            function openTab(evt, tabName) {
                const tabcontent = document.getElementsByClassName("tabcontent");
                for (let i = 0; i < tabcontent.length; i++) {
                    tabcontent[i].style.display = "none";
                }
                
                const tablinks = document.getElementsByClassName("tablinks");
                for (let i = 0; i < tablinks.length; i++) {
                    tablinks[i].className = tablinks[i].className.replace(" active", "");
                }
                
                document.getElementById(tabName).style.display = "block";
                evt.currentTarget.className += " active";
            }
            
            // Debug functions
            function checkCORSConfig() {
                fetch('/api/v1/auth/google/debug-auth', {
                    method: 'OPTIONS'
                })
                .then(response => {
                    const corsHeaders = {
                        'Access-Control-Allow-Origin': response.headers.get('Access-Control-Allow-Origin'),
                        'Access-Control-Allow-Methods': response.headers.get('Access-Control-Allow-Methods'),
                        'Access-Control-Allow-Headers': response.headers.get('Access-Control-Allow-Headers'),
                        'Access-Control-Allow-Credentials': response.headers.get('Access-Control-Allow-Credentials')
                    };
                    
                    document.getElementById('debugOutput').innerHTML = `
                        <h4>CORS Headers</h4>
                        <pre>${JSON.stringify(corsHeaders, null, 2)}</pre>
                    `;
                })
                .catch(error => {
                    document.getElementById('debugOutput').innerHTML = `<p class="error">Error checking CORS: ${error.message}</p>`;
                });
            }
            
            function checkBrowserStorage() {
                // Check localStorage
                const localStorageToken = localStorage.getItem('access_token');
                
                // Check sessionStorage
                const sessionStorageToken = sessionStorage.getItem('access_token');
                
                // Check cookies
                const cookies = document.cookie.split(';');
                let cookieToken = null;
                
                for (const cookie of cookies) {
                    const [name, value] = cookie.trim().split('=');
                    if (name === 'access_token') {
                        cookieToken = value;
                        break;
                    }
                }
                
                document.getElementById('debugOutput').innerHTML = `
                    <h4>Browser Storage Check</h4>
                    <p><strong>localStorage:</strong> ${localStorageToken ? 'Token found' : 'No token'}</p>
                    <p><strong>sessionStorage:</strong> ${sessionStorageToken ? 'Token found' : 'No token'}</p>
                    <p><strong>cookies:</strong> ${cookieToken ? 'Token found' : 'No token'}</p>
                `;
            }
            
            function generateTestRequest() {
                const token = document.getElementById('token').value.trim();
                let cleanToken = token;
                
                // Remove "Bearer " prefix if present
                if (cleanToken.startsWith('Bearer ')) {
                    cleanToken = cleanToken.substring(7);
                }
                
                if (!cleanToken) {
                    document.getElementById('debugOutput').innerHTML = '<p class="error">Please enter a token first</p>';
                    return;
                }
                
                const fetchCode = `fetch('/api/v1/auth/google/verify-token', {
  headers: {
    'Authorization': 'Bearer ${cleanToken}'
  }
})
.then(response => response.json())
.then(data => console.log(data))
.catch(error => console.error(error));`;

                const axiosCode = `axios.get('/api/v1/auth/google/verify-token', {
  headers: {
    'Authorization': \`Bearer ${cleanToken}\`
  }
})
.then(response => console.log(response.data))
.catch(error => console.error(error));`;

                const curlCode = `curl -H "Authorization: Bearer ${cleanToken}" http://localhost:8000/api/v1/auth/google/verify-token`;
                
                document.getElementById('debugOutput').innerHTML = `
                    <h4>Test Requests</h4>
                    <p><strong>Fetch API:</strong></p>
                    <pre>${fetchCode}</pre>
                    
                    <p><strong>Axios:</strong></p>
                    <pre>${axiosCode}</pre>
                    
                    <p><strong>cURL:</strong></p>
                    <pre>${curlCode}</pre>
                `;
            }
            
            // Initialize
            document.addEventListener('DOMContentLoaded', function() {
                // Try to load token from localStorage first
                const token = localStorage.getItem('access_token');
                if (token) {
                    document.getElementById('token').value = token;
                    analyzeToken();
                }
            });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content) 