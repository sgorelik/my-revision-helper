"""
Authentication module with optional Auth0 integration.

Supports both authenticated (via Auth0 JWT) and anonymous users.
Authentication is optional - endpoints work with or without auth.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from typing import Optional, Dict
import os
import requests
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)  # Don't auto-raise on missing token


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

