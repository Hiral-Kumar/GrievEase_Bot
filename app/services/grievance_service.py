"""
Grievance service layer — the actual create/fetch/update logic, extracted so
it can be called from two places without duplicating it:
  1. app/api/grievance.py — the HTTP contract (Section 8 of the docs)
  2. app/core/dialogue_manager.py — the chatbot's Submit/Track flows

In a real deployment, the chatbot would call the core Grievance Management
System over HTTP, exactly as documented in Section 8. Here, both the
"mock system" and the "chatbot" live in the same process/repo for a fast,
self-contained prototype, so the dialogue manager calls this service
directly instead of making a self-referential HTTP request to its own API.
The function signatures below intentionally mirror the API contract 1:1, so
swapping this for a real `httpx` call to an external service later is a
drop-in change at the call site, not a redesign.
"""
from sqlalchemy.orm import Session

from app.models.grievance import Grievance, GrievanceCategory, GrievanceStatus, SENSITIVE_CATEGORIES
from app.services.notification_service import send_notification


class GrievanceNotFound(Exception):
    """Raised when a Ticket ID doesn't match any grievance."""


def create_grievance(
    db: Session, *, student_id: str, student_email: str,
    category: GrievanceCategory, description: str, location: str | None = None,
) -> Grievance:
    grievance = Grievance(
        student_id=student_id,
        student_email=student_email,
        category=category,
        description=description,
        location=location,
        is_sensitive=category in SENSITIVE_CATEGORIES,
    )
    db.add(grievance)
    db.commit()
    db.refresh(grievance)

    send_notification(grievance, event="submitted")
    return grievance


def get_grievance_by_ticket_id(db: Session, ticket_id: str) -> Grievance:
    grievance = db.query(Grievance).filter(Grievance.ticket_id == ticket_id).first()
    if not grievance:
        raise GrievanceNotFound(f"No grievance found with Ticket ID {ticket_id}")
    return grievance


def update_grievance_status(db: Session, ticket_id: str, status: GrievanceStatus) -> Grievance:
    grievance = get_grievance_by_ticket_id(db, ticket_id)
    grievance.status = status
    db.commit()
    db.refresh(grievance)

    send_notification(grievance, event="status_updated")
    return grievance


def list_categories() -> list[str]:
    return [c.value for c in GrievanceCategory]
