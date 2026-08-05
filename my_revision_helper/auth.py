"""
Authentication module with optional Auth0 integration.

Supports both authenticated (via Auth0 JWT) and anonymous users.
Authentication is optional - endpoints work with or without auth.

There is also a personal access token, for scripts and the MCP server. Auth0
tokens are issued to a browser and expire within hours, which is no use to
something running unattended, so a long secret set on the server stands in for
one named account instead.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from typing import Optional, Dict
import os
import secrets
import requests
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)  # Don't auto-raise on missing token

# Short enough to guess is worse than no token at all, because it looks safe.
MIN_TOKEN_LENGTH = 32


def personal_token_user() -> Optional[Dict[str, str]]:
    """
    The account the personal access token stands for, if one is configured.

    Both halves are needed: the secret to present, and the Auth0 user id it
    acts as. Without the second, a script would land in its own empty world
    rather than alongside the work done in the browser.
    """
    token = os.getenv("API_TOKEN", "").strip()
    user_id = os.getenv("API_TOKEN_USER_ID", "").strip()

    if not token or not user_id:
        return None

    if len(token) < MIN_TOKEN_LENGTH:
        logger.error(
            f"API_TOKEN is too short to be safe ({len(token)} characters, "
            f"{MIN_TOKEN_LENGTH} needed) — ignoring it"
        )
        return None

    return {"user_id": user_id, "token": token}


def _matches_personal_token(presented: str) -> Optional[Dict[str, str]]:
    """Whether this is the personal access token, compared in constant time."""
    configured = personal_token_user()
    if not configured:
        return None

    if not secrets.compare_digest(presented, configured["token"]):
        return None

    return {
        "user_id": configured["user_id"],
        "email": None,
        "name": None,
        "picture": None,
    }


@lru_cache()
def get_jwks():
    """Fetch Auth0 JWKS (JSON Web Key Set) for token verification."""
    auth0_domain = os.getenv("AUTH0_DOMAIN")
    if not auth0_domain:
        return None
    
    try:
        jwks_url = f"https://{auth0_domain}/.well-known/jwks.json"
        response = requests.get(jwks_url, timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.warning(f"Failed to fetch Auth0 JWKS: {e}")
        return None


def get_rsa_key(token: str, jwks: dict):
    """Get RSA key from JWKS for token verification."""
    try:
        unverified_header = jwt.get_unverified_header(token)
        rsa_key = {}
        for key in jwks["keys"]:
            if key["kid"] == unverified_header["kid"]:
                rsa_key = {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n": key["n"],
                    "e": key["e"]
                }
        return rsa_key
    except Exception:
        return None


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[Dict[str, str]]:
    """
    Verify JWT token if provided, return user info or None.
    
    This allows endpoints to work with or without authentication.
    Returns None if:
    - No token provided
    - Auth0 not configured
    - Token is invalid
    
    Returns user dict with user_id, email, name, picture if valid.
    """
    # No token provided - user is not authenticated
    if not credentials:
        return None
    
    token = credentials.credentials

    # Checked before Auth0, because it is not a JWT and needs to work on a
    # deployment where Auth0 is not configured at all.
    personal = _matches_personal_token(token)
    if personal:
        logger.info(f"Request authenticated by personal access token as {personal['user_id']}")
        return personal

    auth0_domain = os.getenv("AUTH0_DOMAIN")
    auth0_audience = os.getenv("AUTH0_AUDIENCE")
    
    if not auth0_domain or not auth0_audience:
        # Auth0 not configured - treat as unauthenticated
        logger.debug("Auth0 not configured - treating as unauthenticated")
        return None
    
    try:
        jwks = get_jwks()
        if not jwks:
            logger.warning("Could not fetch JWKS - treating as unauthenticated")
            return None
            
        rsa_key = get_rsa_key(token, jwks)
        
        if rsa_key:
            payload = jwt.decode(
                token,
                rsa_key,
                algorithms=["RS256"],
                audience=auth0_audience,
                issuer=f"https://{auth0_domain}/"
            )
            
            return {
                "user_id": payload.get("sub"),
                "email": payload.get("email"),
                "name": payload.get("name"),
                "picture": payload.get("picture"),
            }
    except JWTError as e:
        logger.debug(f"JWT validation failed: {e}")
        # Invalid token - treat as unauthenticated
        return None
    except Exception as e:
        logger.warning(f"Unexpected error during auth: {e}")
        return None
    
    return None


async def get_current_user_required(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, str]:
    """
    Require authentication - raises 401 if not authenticated.
    
    Use this for endpoints that MUST have auth (like user profile).
    """
    user = await get_current_user_optional(credentials)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return user

