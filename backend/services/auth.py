"""Minimal Clerk session-token verification for protected API routes."""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from threading import Lock
from urllib.parse import urlparse

import jwt
from fastapi import Header, HTTPException, status
from jwt import PyJWKClient


@dataclass(frozen=True)
class CurrentUser:
    """The small identity surface the backend needs for community features."""

    user_id: str
    username: str | None = None


_jwks_clients: dict[str, PyJWKClient] = {}
_jwks_lock = Lock()
logger = logging.getLogger(__name__)

# Clerk tokens can be issued a few seconds before/after the local machine
# clock. A small, bounded leeway prevents normal clock drift from making a
# valid signed-in user look logged out. Keep this configurable for deployment.
try:
    JWT_CLOCK_SKEW_SECONDS = max(0, int(os.getenv("CLERK_JWT_CLOCK_SKEW_SECONDS", "120")))
except ValueError:
    JWT_CLOCK_SKEW_SECONDS = 120


def _issuer_from_token(token: str) -> str:
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except jwt.InvalidTokenError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="That sign-in session is not valid.") from error

    issuer = str(claims.get("iss", "")).strip().rstrip("/")
    configured_issuer = os.getenv("CLERK_JWT_ISSUER", "").strip().rstrip("/")
    if configured_issuer:
        if issuer != configured_issuer:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="That sign-in session belongs to another application.")
        return configured_issuer

    parsed = urlparse(issuer)
    hostname = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or not hostname.endswith(".clerk.accounts.dev"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="A Clerk session issuer is not configured for this app.")
    return issuer


def _jwks_client(issuer: str) -> PyJWKClient:
    with _jwks_lock:
        client = _jwks_clients.get(issuer)
        if client is None:
            client = PyJWKClient(f"{issuer}/.well-known/jwks.json")
            _jwks_clients[issuer] = client
        return client


def _replace_jwks_client(issuer: str) -> PyJWKClient:
    """Discard a cached Clerk key client after a failed key lookup."""

    with _jwks_lock:
        client = PyJWKClient(f"{issuer}/.well-known/jwks.json")
        _jwks_clients[issuer] = client
        return client


def verify_session_token(token: str) -> CurrentUser:
    """Verify a Clerk session token supplied by HTTP or WebSocket clients."""

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to use private messages.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    issuer = _issuer_from_token(token)
    try:
        try:
            signing_key = _jwks_client(issuer).get_signing_key_from_jwt(token)
        except (jwt.PyJWTError, OSError, ValueError):
            # Clerk can rotate signing keys while this process is running.
            # Retry once with a newly-created client before rejecting a valid
            # session as though it had expired.
            signing_key = _replace_jwks_client(issuer).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            leeway=JWT_CLOCK_SKEW_SECONDS,
            options={"verify_aud": False},
        )
    except jwt.ExpiredSignatureError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your sign-in session has expired. Sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    except (jwt.PyJWTError, OSError, ValueError) as error:
        # Do not expose token or key details to the browser, but keep a useful
        # server-side reason so configuration/network issues are diagnosable.
        logger.warning("Clerk session verification failed: %s", type(error).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Aegis could not verify your sign-in session. Refresh the page and sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    user_id = str(claims.get("sub", "")).strip()
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="That sign-in session has no user identity.")
    username = claims.get("username")
    return CurrentUser(user_id=user_id, username=str(username).strip() if username else None)


def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    """Verify the Clerk bearer token sent by the browser."""

    if not authorization or not authorization.casefold().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to use private messages.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verify_session_token(authorization[7:].strip())
