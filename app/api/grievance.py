"""
Mock Grievance Management API.

This implements the exact contract described in the Day 1 documentation
(Section 8 — Integration with the Grievance Management System), standing in
for the core Web Development (Experienced) team's backend so the chatbot can
be built and demoed end-to-end independently.

The actual create/fetch/update logic lives in app/services/grievance_service.py
so the dialogue manager (Step 4) can reuse it without a self-referential HTTP
call — this router is just the HTTP-facing contract layer.

Endpoints:
  POST   /api/grievance                    -> create a grievance, returns Ticket ID
  GET    /api/grievance/categories          -> list valid categories
  GET    /api/grievance/{ticket_id}         -> fetch status
  PATCH  /api/grievance/{ticket_id}/status  -> admin-side status update (triggers notification)
  POST   /api/notify                        -> manually trigger a notification event
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas import (
    GrievanceCreate, GrievanceResponse, GrievanceStatusResponse,
    GrievanceStatusUpdate, CategoryListResponse, NotifyRequest, NotifyResponse,
)
from app.services import grievance_service as svc
from app.services.notification_service import send_notification

router = APIRouter(prefix="/api", tags=["grievance"])


@router.get("/grievance/categories", response_model=CategoryListResponse)
def list_categories():
    """Returns the fixed category list — kept in sync with the Admin Dashboard's own list."""
    return {"categories": svc.list_categories()}


@router.post("/grievance", response_model=GrievanceResponse, status_code=201)
def create_grievance(payload: GrievanceCreate, db: Session = Depends(get_db)):
    """
    Creates a new grievance and sends the mandatory 'Grievance Submitted' email.
    Sensitive categories (see docs, Section 12) are auto-flagged for priority
    human review rather than routine bot/admin handling.
    """
    return svc.create_grievance(
        db,
        student_id=payload.student_id,
        student_email=payload.student_email,
        category=payload.category,
        description=payload.description,
        location=payload.location,
    )


@router.get("/grievance/{ticket_id}", response_model=GrievanceStatusResponse)
def get_grievance_status(ticket_id: str, db: Session = Depends(get_db)):
    """Fetch current status by Ticket ID — the core lookup the chatbot calls for 'track status'."""
    try:
        return svc.get_grievance_by_ticket_id(db, ticket_id)
    except svc.GrievanceNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/grievance/{ticket_id}/status", response_model=GrievanceResponse)
def update_grievance_status_endpoint(ticket_id: str, payload: GrievanceStatusUpdate, db: Session = Depends(get_db)):
    """
    Admin-side status update (Pending / In Progress / Resolved). Triggers the
    mandatory 'Status Updated' email — mirrors the Admin Dashboard action from
    the challenge's core feature list.
    """
    try:
        return svc.update_grievance_status(db, ticket_id, payload.status)
    except svc.GrievanceNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/notify", response_model=NotifyResponse)
def trigger_notification(payload: NotifyRequest, db: Session = Depends(get_db)):
    """
    Manually trigger a notification for a given ticket + event. Mostly useful
    for testing the notification service in isolation, or for the chatbot to
    (re)trigger a confirmation if a student asks "did my email go through?".
    """
    try:
        grievance = svc.get_grievance_by_ticket_id(db, payload.ticket_id)
    except svc.GrievanceNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    return send_notification(grievance, event=payload.event)
