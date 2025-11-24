import logging
logger = logging.getLogger(__name__)

def send_set_password_email(email: str, link: str):
    # DEV: just log it. In prod, integrate Postmark/Resend/Mailgun.
    logger.info("Set-password email to %s: %s", email, link)
