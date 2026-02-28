import logging
import smtplib
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def send_email(
    subject: str,
    body: str,
    to_email: str,
    from_email: str,
    app_password: str,
) -> None:
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(from_email, app_password)
        server.sendmail(from_email, to_email, msg.as_string())


def notify_booking_result(
    success: bool,
    details: str,
    notifications_config,
    gmail_app_password: str,
    from_email: str,
) -> None:
    if not notifications_config or not notifications_config.enabled:
        return

    if not gmail_app_password:
        logger.warning("Notifications enabled but no gmail_app_password configured")
        return

    subject = "Resy Bot: Booking Successful!" if success else "Resy Bot: Booking Failed"
    body = details

    try:
        send_email(
            subject=subject,
            body=body,
            to_email=notifications_config.email,
            from_email=from_email,
            app_password=gmail_app_password,
        )
        logger.info(f"Notification email sent to {notifications_config.email}")
    except Exception as e:
        logger.error(f"Failed to send notification email: {e}")
