"""
Pydantic schemas — these define the exact request/response shapes for the API,
matching the contract laid out in the Day 1 documentation (Section 8).
Keeping these separate from the SQLAlchemy models means the API's public
contract can stay stable even if the internal DB schema changes later.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field

from app.models.grievance import GrievanceCategory, GrievanceStatus


class GrievanceCreate(BaseModel):
    student_id: str = Field(..., description="Authenticated student's ID/roll number")
    student_email: EmailStr = Field(..., description="Where confirmation/status emails are sent")
    category: GrievanceCategory
    description: str = Field(..., min_length=10, max_length=2000)
    location: Optional[str] = Field(None, description="Hostel block/room, department, etc.")


class GrievanceResponse(BaseModel):
    ticket_id: str
    student_id: str
    category: GrievanceCategory
    description: str
    location: Optional[str]
    status: GrievanceStatus
    is_sensitive: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GrievanceStatusResponse(BaseModel):
    ticket_id: str
    category: GrievanceCategory
    status: GrievanceStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GrievanceStatusUpdate(BaseModel):
    status: GrievanceStatus


class CategoryListResponse(BaseModel):
    categories: list[str]


class NotifyRequest(BaseModel):
    ticket_id: str
    event: str = Field(..., description="'submitted' or 'status_updated'")


class NotifyResponse(BaseModel):
    sent: bool
    to: str
    subject: str
