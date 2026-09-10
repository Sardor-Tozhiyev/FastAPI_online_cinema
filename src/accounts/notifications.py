"""
Email notification helpers.

In this reference implementation, sending is abstracted behind `send_email` so it can be:
- called synchronously in tests (monkeypatched),
- delegated to a Celery task in production for async delivery.

Replace the body of `send_email` with a real SMTP/SES integration when going to production.
"""
import logging

from src.config import settings

logger = logging.getLogger("online_cinema.notifications")


def send_email(to: str, subject: str, body: str) -> None:
    """Send a single email. Currently, logs; swap for real SMTP client in production."""
    logger.info("Sending email to=%s, subject=%s", to, subject)
    logger.debug("Email body: \n%s", body)


def build_activation_link(email: str, token: str) -> str:
    return f"{settings.FRONTEND_URL}/activate?email={email}&token={token}"


def build_password_reset_link(email: str, token: str) -> str:
    return f"{settings.FRONTEND_URL}/reset-password?email={email}&token={token}"


def send_activation_email(email: str, token: str) -> None:
    link = build_activation_link(email, token)
    send_email(
        to=email,
        subject="Activate your Online Cinema account",
        body=f"Click the link to activate your account (valid for 24 hours): {link}",
    )


def send_password_reset_email(email: str, token: str) -> None:
    link = build_password_reset_link(email, token)
    send_email(
        to=email,
        subject="Reset your Online Cinema password",
        body=f"Click the link to reset your password: {link}",
    )


def send_order_confirmation_email(email: str,order_id: int, amount: str) -> None:
    send_email(
        to=email,
        subject=f"Payment confirmation — order #{order_id}",
        body=f"Your payment of {amount} for order #{order_id} was successful. Thank you!",
    )
