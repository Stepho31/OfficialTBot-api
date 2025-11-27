import logging
import smtplib
from email.message import EmailMessage
from typing import Optional

from app.settings import settings

logger = logging.getLogger(__name__)


def _smtp_configured() -> bool:
    """Quick helper to confirm SMTP credentials exist."""
    return (
        bool(settings.SMTP_HOST)
        and bool(settings.EMAIL_FROM)
        and bool(settings.SMTP_PORT)
    )


def _send_email(subject: str, body: str, to_email: str) -> None:
    """
    Send an email using the configured SMTP relay.
    Falls back to logging when SMTP is not configured.
    """
    if not _smtp_configured():
        logger.warning(
            "SMTP not configured. Email to %s logged instead of sent. Subject=%s",
            to_email,
            subject,
        )
        logger.info("Email body for %s: %s", to_email, body)
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to_email
    msg.set_content(body)

    try:
        if settings.SMTP_USE_SSL:
            server: Optional[smtplib.SMTP] = smtplib.SMTP_SSL(
                settings.SMTP_HOST, settings.SMTP_PORT
            )
        else:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
            server.ehlo()
            if settings.SMTP_USE_TLS:
                server.starttls()

        if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)

        server.send_message(msg)
        logger.info("Email sent to %s. Subject=%s", to_email, subject)
    except Exception:
        logger.exception("Failed to send email to %s", to_email)
        raise
    finally:
        try:
            server.quit()
        except Exception:
            pass


def send_set_password_email(email: str, link: str):
    subject = "Set Your Autopip AI Password"
    body = (
        "Welcome to Autopip AI!\n\n"
        "Please set your password using the secure link below:\n"
        f"{link}\n\n"
        "This link expires in 24 hours. If you did not request this, please ignore."
    )
    _send_email(subject, body, email)


def send_password_reset_email(email: str, link: str):
    """
    Send password reset email to user using configured SMTP relay.
    """
    subject = "Reset Your Autopip AI Password"
    body = (
        "We received a request to reset your Autopip AI password.\n\n"
        "You can set a new password by clicking the link below:\n"
        f"{link}\n\n"
        "This link will expire in 60 minutes.\n"
        "If you did not request a password reset, please ignore this email."
    )
    _send_email(subject, body, email)
