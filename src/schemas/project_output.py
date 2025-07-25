"""
Schemas for project outputs.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ProjectOutputBase(BaseModel):
    """Base schema for project output."""
    output_name: str = Field(..., description="Name of the output")
    comments_allowed_on_output: bool = Field(True, description="Whether comments are allowed on this output")


class ProjectOutputCreate(BaseModel):
    """Schema for creating a project output."""
    name: str = Field(..., description="Name of the output")
    deliverable_id: UUID = Field(..., description="ID of the deliverable")
    description: Optional[str] = Field(None, description="Description of the output")
    type: Optional[str] = Field(None, description="Type of the output")
    file_path: Optional[str] = Field(None, description="Path to the output file")
    project_id: Optional[UUID] = Field(None, description="ID of the project")


class ProjectOutputUpdate(BaseModel):
    """Schema for updating a project output."""
    output_name: Optional[str] = Field(None, description="Name of the output")
    output_url: Optional[str] = Field(None, description="URL to the output")
    comments_allowed_on_output: Optional[bool] = Field(None, description="Whether comments are allowed on this output")


class ProjectOutputResponse(ProjectOutputBase):
    """Schema for project output response."""
    id: UUID = Field(..., description="ID of the output")
    deliverable_id: UUID = Field(..., description="ID of the deliverable")
    project_id: UUID = Field(..., description="ID of the project")
    output_url: Optional[str] = Field(None, description="URL to the output")
    delivery_date: Optional[datetime] = Field(None, description="Date when the output was delivered")
    created_at: datetime = Field(..., description="Date when the output was created")
    updated_at: Optional[datetime] = Field(None, description="Date when the output was last updated")

    class Config:
        orm_mode = True


class ProjectCompilationResponse(BaseModel):
    """Schema for project compilation response."""
    project_id: UUID = Field(..., description="ID of the project")
    compilation_started: bool = Field(..., description="Whether compilation has started")
    compilation_url: Optional[str] = Field(None, description="URL to the compiled project package")