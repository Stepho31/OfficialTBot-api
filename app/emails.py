# import logging
# import smtplib
# from email.message import EmailMessage
# from typing import Optional

# from app.settings import settings

# logger = logging.getLogger(__name__)


# def _smtp_configured() -> bool:
#     """Quick helper to confirm SMTP credentials exist."""
#     return (
#         bool(settings.SMTP_HOST)
#         and bool(settings.EMAIL_FROM)
#         and bool(settings.SMTP_PORT)
#     )


# def _send_email(subject: str, body: str, to_email: str) -> None:
#     """
#     Send an email using the configured SMTP relay.
#     Falls back to logging when SMTP is not configured.
#     """
#     if not _smtp_configured():
#         logger.warning(
#             "SMTP not configured. Email to %s logged instead of sent. Subject=%s",
#             to_email,
#             subject,
#         )
#         logger.info("Email body for %s: %s", to_email, body)
#         return

#     msg = EmailMessage()
#     msg["Subject"] = subject
#     msg["From"] = settings.EMAIL_FROM
#     msg["To"] = to_email
#     msg.set_content(body)

#     try:
#         if settings.SMTP_USE_SSL:
#             server: Optional[smtplib.SMTP] = smtplib.SMTP_SSL(
#                 settings.SMTP_HOST, settings.SMTP_PORT
#             )
#         else:
#             server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
#             server.ehlo()
#             if settings.SMTP_USE_TLS:
#                 server.starttls()

#         if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
#             server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)

#         server.send_message(msg)
#         logger.info("Email sent to %s. Subject=%s", to_email, subject)
#     except Exception:
#         logger.exception("Failed to send email to %s", to_email)
#         raise
#     finally:
#         try:
#             server.quit()
#         except Exception:
#             pass


# def send_set_password_email(email: str, link: str):
#     subject = "Set Your Autopip AI Password"
#     body = (
#         "Welcome to Autopip AI!\n\n"
#         "Please set your password using the secure link below:\n"
#         f"{link}\n\n"
#         "This link expires in 24 hours. If you did not request this, please ignore."
#     )
#     _send_email(subject, body, email)


# def send_password_reset_email(email: str, link: str):
#     """
#     Send password reset email to user using configured SMTP relay.
#     """
#     subject = "Reset Your Autopip AI Password"
#     body = (
#         "We received a request to reset your Autopip AI password.\n\n"
#         "You can set a new password by clicking the link below:\n"
#         f"{link}\n\n"
#         "This link will expire in 60 minutes.\n"
#         "If you did not request a password reset, please ignore this email."
#     )
#     _send_email(subject, body, email)
import logging
import smtplib
from email.message import EmailMessage

from app.settings import settings

logger = logging.getLogger(__name__)


def _send_email(subject: str, body: str, recipient: str) -> None:
    """
    Low-level email sender using SMTP.
    Selects TLS/SSL mode based on SMTP_PORT:
      - 465: SMTP over SSL
      - anything else: SMTP + STARTTLS
    """
    host = settings.SMTP_HOST
    port = settings.SMTP_PORT
    username = settings.SMTP_USERNAME
    password = settings.SMTP_PASSWORD
    from_addr = settings.EMAIL_FROM

    if not host or not port:
        logger.warning("SMTP is not configured (host/port missing); skipping email send.")
        return

    # In case port is stored as string in env/settings
    try:
        port_int = int(port)
    except (TypeError, ValueError):
        logger.error("Invalid SMTP_PORT value: %r", port)
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = recipient
    msg.set_content(body)

    if port_int == 465:
        # SSL directly
        with smtplib.SMTP_SSL(host, port_int) as server:
            if username and password:
                server.login(username, password)
            server.send_message(msg)
    else:
        # Default: STARTTLS (e.g. port 587)
        with smtplib.SMTP(host, port_int) as server:
            server.ehlo()
            try:
                server.starttls()
                server.ehlo()
            except smtplib.SMTPException:
                # Some providers may not require/allow STARTTLS; log and continue
                logger.warning("STARTTLS failed or not supported; continuing without TLS.")
            if username and password:
                server.login(username, password)
            server.send_message(msg)


def send_password_reset_email(email: str, reset_link: str) -> None:
    """
    High-level helper for password reset emails.
    Any exception raised here is caught and logged, so callers don't 500.
    """
    subject = "Reset your AutoPip AI password"
    body = (
        "You requested a password reset for your AutoPip AI account.\n\n"
        f"Click the link below to set a new password:\n\n{reset_link}\n\n"
        "If you did not request this, you can safely ignore this email."
    )

    try:
        _send_email(subject, body, email)
    except Exception:
        logger.exception("Failed to send password reset email to %s", email)
        # Do not re-raise: auth.forgot_password will still return success
