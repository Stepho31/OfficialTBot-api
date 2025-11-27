import logging
logger = logging.getLogger(__name__)

def send_set_password_email(email: str, link: str):
    # DEV: just log it. In prod, integrate Postmark/Resend/Mailgun.
    logger.info("Set-password email to %s: %s", email, link)

def send_password_reset_email(email: str, link: str):
    """
    Send password reset email to user.
    In production, integrate with Postmark/Resend/Mailgun/SendGrid.
    """
    # DEV: just log it. In prod, integrate Postmark/Resend/Mailgun.
    logger.info("Password reset email to %s: %s", email, link)
    
    # TODO: In production, implement actual email sending:
    # - Use your email service (Postmark, Resend, Mailgun, SendGrid, etc.)
    # - Format email with proper HTML/text content
    # - Include the reset link
    # - Set proper subject line: "Reset Your Autopip AI Password"
