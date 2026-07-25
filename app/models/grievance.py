"""
The Grievance table. This mirrors what the core Web Development (Experienced)
team's Grievance Management System would own — the chatbot's mock API here
exists so the chatbot can be built and tested independently, against the same
shape of data the real system will expose (see docs, Section 8: Integration).
"""
import enum
import uuid
import random
from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime, Enum as SAEnum, Boolean
from app.core.database import Base


class GrievanceCategory(str, enum.Enum):
    ACADEMIC = "Academic"
    HOSTEL = "Hostel"
    EXAMINATION = "Examination"
    IT_INFRASTRUCTURE = "IT Infrastructure"
    ADMINISTRATIVE = "Administrative"
    FACULTY = "Faculty"
    HARASSMENT_SENSITIVE = "Harassment / Sensitive"


class GrievanceStatus(str, enum.Enum):
    PENDING = "Pending"
    IN_PROGRESS = "In Progress"
    RESOLVED = "Resolved"


# Categories that must always be flagged for immediate human attention rather
# than routine bot-driven handling (see docs, Section 12 — Security & Escalation).
SENSITIVE_CATEGORIES = {GrievanceCategory.HARASSMENT_SENSITIVE}


def generate_ticket_id() -> str:
    """
    Produces IDs in the same GBU-YYYY-###### format shown in the Day 1 docs
    (e.g. GBU-2026-004821). Random 6-digit suffix keeps this simple for a
    prototype; a production system would use a DB sequence instead to
    guarantee no collisions.
    """
    year = datetime.utcnow().year
    suffix = f"{random.randint(0, 999999):06d}"
    return f"GBU-{year}-{suffix}"


class Grievance(Base):
    __tablename__ = "grievances"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id = Column(String, unique=True, index=True, nullable=False, default=generate_ticket_id)

    student_id = Column(String, nullable=False, index=True)
    student_email = Column(String, nullable=False)

    category = Column(SAEnum(GrievanceCategory), nullable=False)
    description = Column(Text, nullable=False)
    location = Column(String, nullable=True)  # e.g. hostel block/room, department

    status = Column(SAEnum(GrievanceStatus), nullable=False, default=GrievanceStatus.PENDING)
    is_sensitive = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
