from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OmniDimensionError(RuntimeError):
    """A safe, user-facing error from the OmniDimension API."""


def create_web_session(
    custom_variables: dict[str, str],
    agent_env_name: str = "OMNIDIM_AGENT_ID",
) -> dict[str, object]:
    """Create a short-lived browser voice session without exposing our API key.

    Different Aegis experiences use different OmniDimension agents. Keeping the
    environment-variable name explicit prevents a trusted-contact prompt from
    accidentally being used for the companion conversation.
    """

    api_key = os.getenv("OMNIDIM_API_KEY", "").strip()
    if not api_key:
        raise OmniDimensionError("OMNIDIM_API_KEY is not configured in backend/.env")

    raw_agent_id = os.getenv(agent_env_name, "").strip().lstrip("#")
    if not raw_agent_id.isdigit():
        raise OmniDimensionError(f"{agent_env_name} must be the numeric OmniDimension agent id")

    base_url = os.getenv("OMNIDIM_BASE_URL", "https://omnidim.io/api/v1").strip().rstrip("/")
    payload = json.dumps(
        {
            "agent_id": int(raw_agent_id),
            "type": "voice",
            "custom_variables": custom_variables,
        }
    ).encode("utf-8")
    request = Request(
        f"{base_url}/sessions/create",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=20) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as error:
        # Keep provider credentials and raw provider payloads out of the UI/logs.
        if error.code in {401, 403}:
            raise OmniDimensionError("OmniDimension rejected the API key or agent configuration") from error
        if error.code in {402, 409}:
            raise OmniDimensionError("OmniDimension cannot start a voice session because the account limit or balance was reached") from error
        raise OmniDimensionError(f"OmniDimension could not start the browser voice session (HTTP {error.code})") from error
    except URLError as error:
        raise OmniDimensionError("Aegis could not reach OmniDimension. Check your internet connection") from error
    except TimeoutError as error:
        raise OmniDimensionError("OmniDimension took too long to start the browser voice session") from error

    try:
        response_data = json.loads(response_body)
    except json.JSONDecodeError as error:
        raise OmniDimensionError("OmniDimension returned an unexpected session response") from error

    ws_url = response_data.get("ws_url") if isinstance(response_data, dict) else None
    if not isinstance(ws_url, str) or not ws_url.startswith("wss://"):
        raise OmniDimensionError("OmniDimension did not return a valid browser session URL")

    return {
        "ws_url": ws_url,
        "session_id": response_data.get("session_id") if isinstance(response_data, dict) else None,
        "expires_at": response_data.get("expires_at") if isinstance(response_data, dict) else None,
    }
