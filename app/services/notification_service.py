"""
Notification service — handles the two mandatory email events from the
challenge brief: Grievance Submitted and Status Updated.

For local development / grading, if no real SMTP credentials are set in .env,
emails are logged instead of sent — so the whole flow runs end-to-end out of
the box without requiring a real mail server. Swapping in real SMTP is just
enabling the `_send_via_smtp` path once credentials are configured.
"""
import logging
import smtplib
from email.mime.text import MIMEText

from app.core.config import settings
from app.models.grievance import Grievance

logger = logging.getLogger("grievease.notifications")
logging.basicConfig(level=logging.INFO)

# In-memory record of sent notifications — handy for tests and for an
# admin-side "notification log" view without needing a separate table.
SENT_LOG: list[dict] = []


def _subject_and_body(grievance: Grievance, event: str) -> tuple[str, str]:
    if event == "submitted":
        subject = f"Grievance Received — Ticket {grievance.ticket_id}"
        body = (
            f"Dear Student,\n\n"
            f"Your grievance has been received and logged under Ticket ID "
            f"{grievance.ticket_id} (Category: {grievance.category.value}).\n"
            f"Current Status: {grievance.status.value}.\n\n"
            f"You can track updates anytime using this Ticket ID.\n\n"
            f"— GBU IT Cell Grievance Management System"
        )
    elif event == "status_updated":
        subject = f"Grievance Status Updated — Ticket {grievance.ticket_id}"
        body = (
            f"Dear Student,\n\n"
            f"Your grievance {grievance.ticket_id} has a new status: "
            f"{grievance.status.value}.\n\n"
            f"— GBU IT Cell Grievance Management System"
        )
    else:
        raise ValueError(f"Unknown notification event: {event}")
    return subject, body


def _send_via_smtp(to_email: str, subject: str, body: str) -> None:
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings.NOTIFY_FROM_EMAIL
    msg["To"] = to_email

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.NOTIFY_FROM_EMAIL, [to_email], msg.as_string())


def send_notification(grievance: Grievance, event: str) -> dict:
    """
    Sends (or logs) a notification email for the given grievance + event.
    Returns a dict describing what was sent, used directly in the API response.
    """
    subject, body = _subject_and_body(grievance, event)

    if settings.SMTP_CONFIGURED:
        _send_via_smtp(grievance.student_email, subject, body)
        sent = True
    else:
        logger.info(
            "[MOCK EMAIL] To: %s | Subject: %s\n%s",
            grievance.student_email, subject, body,
        )
        sent = True  # mock-sent, i.e. successfully logged

    record = {"ticket_id": grievance.ticket_id, "to": grievance.student_email,
              "subject": subject, "event": event}
    SENT_LOG.append(record)
    return {"sent": sent, "to": grievance.student_email, "subject": subject}
