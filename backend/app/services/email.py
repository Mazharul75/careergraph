"""Sending email — abstracted the same way the task queue and repositories are.

**Why a protocol for something this small.** A unit test of ``AuthService.register`` should
not need a Resend API key, a network connection, or a real inbox to assert that a verification
token was created. Depending on an ``EmailSenderProtocol`` rather than importing Resend
directly is what lets a test substitute a recorder and check "an email would have been sent to
this address with this link in it" — the same reasoning as ``TaskDispatcher``.

**Why this degrades instead of failing.** No Resend account is required to run this project
locally or in CI. Unset ``RESEND_API_KEY`` selects ``LoggingEmailSender``, which writes the
message to the log instead of sending it — the verification *token* still exists and still
works against ``/auth/verify-email``, only the delivery mechanism differs.
"""

from __future__ import annotations

import logging
from typing import Protocol

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_RESEND_API_URL = "https://api.resend.com/emails"


class EmailSenderProtocol(Protocol):
    async def send(self, *, to: str, subject: str, html: str) -> None: ...


class ResendEmailSender:
    """Sends through Resend's REST API directly, via ``httpx``.

    One POST request, so a full SDK would be a dependency for a single function call. Failures
    are logged and swallowed rather than raised: a registration must succeed even if the email
    provider is down, because the user can always ask for the link again via
    ``/auth/resend-verification`` once it recovers.
    """

    def __init__(self, *, api_key: str, from_address: str) -> None:
        self._api_key = api_key
        self._from = from_address

    async def send(self, *, to: str, subject: str, html: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    _RESEND_API_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={"from": self._from, "to": [to], "subject": subject, "html": html},
                )
                response.raise_for_status()
        except httpx.HTTPError:
            logger.exception("Failed to send email to %s via Resend", to)


class LoggingEmailSender:
    """The local/CI fallback: writes the email to the log instead of sending it.

    Selected automatically when no ``RESEND_API_KEY`` is configured — see ``get_email_sender``.
    A developer running the stack locally can read the verification link straight out of the
    API container's log without ever creating an email account.
    """

    async def send(self, *, to: str, subject: str, html: str) -> None:
        logger.info("EMAIL (no provider configured) to=%s subject=%r\n%s", to, subject, html)


def get_email_sender() -> EmailSenderProtocol:
    settings = get_settings()
    if settings.resend_api_key is not None:
        return ResendEmailSender(
            api_key=settings.resend_api_key.get_secret_value(),
            from_address=settings.email_from,
        )
    return LoggingEmailSender()


def verification_email_html(*, full_name: str | None, verify_url: str) -> str:
    greeting = f"Hi {full_name.split(' ')[0]}," if full_name else "Hi,"
    return (
        f"<p>{greeting}</p>"
        f"<p>Confirm your email address for CareerGraph:</p>"
        f'<p><a href="{verify_url}">{verify_url}</a></p>'
        f"<p>This link expires in 24 hours. If you did not create an account, ignore this "
        f"email.</p>"
    )


def password_reset_email_html(*, full_name: str | None, reset_url: str) -> str:
    greeting = f"Hi {full_name.split(' ')[0]}," if full_name else "Hi,"
    return (
        f"<p>{greeting}</p>"
        f"<p>Someone requested a password reset for your CareerGraph account. If this was "
        f"you, choose a new password here:</p>"
        f'<p><a href="{reset_url}">{reset_url}</a></p>'
        f"<p>This link expires in one hour and can be used once. If you did not request "
        f"this, your password has not been changed and you can safely ignore this email.</p>"
    )
