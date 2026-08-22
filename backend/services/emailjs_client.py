"""EmailJS sender for consented Aegis help emails."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class EmailJSError(RuntimeError):
    """A safe, user-facing error from EmailJS."""


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _is_enabled(value: str | None, default: bool = False) -> bool:
    cleaned = _clean(value).casefold()
    if not cleaned:
        return default
    return cleaned in {"1", "true", "yes", "on"}


def _required_config(name: str) -> str:
    value = _clean(os.getenv(name))
    if not value:
        raise EmailJSError(f"{name} is not configured in backend/.env")
    return value


def _valid_email(value: str) -> bool:
    return len(value) <= 254 and bool(EMAIL_PATTERN.fullmatch(value))


def validate_email_recipient(recipient_type: str, trusted_email: str | None) -> None:
    """Validate user-entered recipient data before placing it in the outbox."""

    if recipient_type == "trusted":
        if not _valid_email(_clean(trusted_email).casefold()):
            raise EmailJSError("Please enter a valid trusted contact email address")
        return
    if recipient_type != "women_support":
        raise EmailJSError("Choose a valid email recipient type")


def email_recipient_metadata(recipient_type: str, trusted_email: str | None = None) -> dict[str, object]:
    """Return safe UI metadata without resolving or sending the message."""

    validate_email_recipient(recipient_type, trusted_email)
    return {
        "recipient_type": recipient_type,
        "recipient_label": "Trusted contact" if recipient_type == "trusted" else "Women’s support authority",
        "demo_mode": _is_enabled(os.getenv("EMAIL_DEMO_MODE"), default=True) and recipient_type == "women_support",
    }


def _provider_error_detail(error: HTTPError) -> str:
    """Read a short, non-secret provider explanation for troubleshooting."""
    try:
        body = error.read().decode("utf-8", errors="replace")
    except Exception:
        return ""
    detail = " ".join(body.split())
    return detail[:240]


def send_email_alert(
    *,
    recipient_type: str,
    trusted_email: str | None,
    user_name: str,
    location: str | None,
    situation: str | None,
    instructions: str | None,
    chat_summary: str | None,
) -> dict[str, object]:
    """Send a predefined EmailJS template without exposing provider secrets."""

    service_id = _required_config("EMAILJS_SERVICE_ID")
    template_id = _required_config("EMAILJS_TEMPLATE_ID")
    public_key = _required_config("EMAILJS_PUBLIC_KEY")
    private_key = _clean(os.getenv("EMAILJS_PRIVATE_KEY"))
    demo_mode = _is_enabled(os.getenv("EMAIL_DEMO_MODE"), default=True)

    validate_email_recipient(recipient_type, trusted_email)
    if recipient_type == "trusted":
        recipient_email = _clean(trusted_email).casefold()
        recipient_label = "Trusted contact"
    elif recipient_type == "women_support":
        recipient_label = "Women’s support authority"
        if demo_mode:
            recipient_email = _clean(os.getenv("EMAIL_DEMO_RECIPIENT")).casefold()
            if not _valid_email(recipient_email):
                raise EmailJSError("EMAIL_DEMO_RECIPIENT is not configured with a valid email address")
        else:
            recipient_email = _clean(os.getenv("EMAIL_WOMEN_SUPPORT_RECIPIENT")).casefold()
            if not _valid_email(recipient_email):
                raise EmailJSError("EMAIL_WOMEN_SUPPORT_RECIPIENT is not configured with a valid email address")
    safe_user_name = _clean(user_name)
    safe_location = _clean(location) or "Not provided"
    safe_situation = _clean(situation) or "No separate situation message was provided."
    safe_instructions = _clean(instructions) or "Please review this request and respond if you can safely help."
    safe_summary = _clean(chat_summary) or "No chat summary was provided."
    demo_notice = (
        "DEMO ONLY: this message was routed to the Aegis demo inbox, not to a real authority."
        if demo_mode and recipient_type == "women_support"
        else ""
    )
    subject_prefix = "[DEMO] " if demo_mode and recipient_type == "women_support" else ""

    template_params = {
        "to_email": recipient_email,
        "to_name": recipient_label,
        "from_name": "Aegis Safety Support",
        "subject": f"{subject_prefix}Aegis help request from {safe_user_name}",
        "recipient_type": recipient_label,
        "user_name": safe_user_name,
        "location": safe_location,
        "situation": safe_situation,
        "instructions": safe_instructions,
        "chat_summary": safe_summary,
        "demo_notice": demo_notice,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }
    request_payload = {
        "service_id": service_id,
        "template_id": template_id,
        "user_id": public_key,
        "template_params": template_params,
    }
    # EmailJS strict API mode requires the account private key. Keep it in the
    # backend environment only; never return it to the browser or API response.
    if private_key:
        request_payload["accessToken"] = private_key
    request_body = json.dumps(request_payload).encode("utf-8")
    request = Request(
        "https://api.emailjs.com/api/v1.0/email/send",
        data=request_body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            # EmailJS is fronted by Cloudflare; identify this as a normal app client
            # instead of urllib's default Python user agent.
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36 Aegis",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=15) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as error:
        if error.code in {401, 403}:
            provider_detail = _provider_error_detail(error)
            message = "EmailJS rejected the configured service or public key"
            if provider_detail:
                message = f"{message}: {provider_detail}"
            raise EmailJSError(message) from error
        if error.code == 429:
            raise EmailJSError("EmailJS is rate-limiting requests. Please wait before trying again") from error
        raise EmailJSError(f"EmailJS could not send the message (HTTP {error.code})") from error
    except URLError as error:
        raise EmailJSError("Aegis could not reach EmailJS. Check the internet connection") from error
    except TimeoutError as error:
        raise EmailJSError("EmailJS took too long to send the message") from error

    if response_body.strip().casefold() not in {"ok", '"ok"'}:
        raise EmailJSError("EmailJS returned an unexpected response")

    return {
        "recipient_type": recipient_type,
        "recipient_label": recipient_label,
        "demo_mode": demo_mode and recipient_type == "women_support",
    }
