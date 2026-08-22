"""Small server-side directory lookup for Clerk username discovery."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import dotenv_values


CLERK_USERS_URL = "https://api.clerk.com/v1/users"
USERNAME_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_.-]{2,63}"


def _clerk_secret_key() -> str:
    configured = os.getenv("CLERK_SECRET_KEY", "").strip()
    if configured:
        return configured

    # During local development the Next.js app already has the server-only
    # Clerk key in frontend/.env.local. Production deployments should set
    # CLERK_SECRET_KEY in the backend environment explicitly.
    frontend_env = Path(__file__).resolve().parents[2] / "frontend" / ".env.local"
    if frontend_env.exists():
        return str(dotenv_values(frontend_env).get("CLERK_SECRET_KEY") or "").strip()
    return ""


def find_username_profiles(query: str, limit: int = 50) -> list[dict[str, str]]:
    """Return Clerk users whose actual username matches the search text.

    A directory outage is intentionally treated as an empty result so the
    caller can still search profiles already saved in Mongo or SQLite.
    """

    secret_key = _clerk_secret_key()
    if not secret_key:
        return []

    normalized_query = query.strip().casefold()
    compact_query = re.sub(r"[\s_.-]+", "", normalized_query)
    params = {"limit": str(min(max(limit, 1), 100)), "order_by": "-created_at"}
    if compact_query:
        params["query"] = compact_query
    request = Request(
        f"{CLERK_USERS_URL}?{urlencode(params)}",
        headers={
            "Authorization": f"Bearer {secret_key}",
            "Accept": "application/json",
            "User-Agent": "AegisBackend/1.0",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=5) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        return []

    if isinstance(payload, dict):
        users = payload.get("data", [])
    elif isinstance(payload, list):
        users = payload
    else:
        users = []
    profiles: list[dict[str, str]] = []
    for user in users:
        if not isinstance(user, dict):
            continue
        username = str(user.get("username") or "").strip()
        compact_username = re.sub(r"[\s_.-]+", "", username.casefold())
        if not username or (compact_query and compact_query not in compact_username):
            continue
        user_id = str(user.get("id") or "").strip()
        if not user_id:
            continue
        name_parts = [str(user.get("first_name") or "").strip(), str(user.get("last_name") or "").strip()]
        display_name = " ".join(part for part in name_parts if part) or username
        profiles.append({"user_id": user_id, "username": username, "display_name": display_name})
    return profiles
