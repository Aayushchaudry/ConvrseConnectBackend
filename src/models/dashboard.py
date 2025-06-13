# src/models/dashboard.py

from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class KPIItem(BaseModel):
    """Schema for individual KPI items in dashboard responses."""
    
    title: str = Field(..., description="Title of the KPI metric")
    value: int | str = Field(..., description="Value of the KPI")
    change: Optional[float] = Field(None, description="Percentage change from previous period")
    change_type: Optional[str] = Field(None, description="Type of change: 'increase' or 'decrease'")
    icon: Optional[str] = Field(None, description="Icon identifier for the KPI")


class TimelineItem(BaseModel):
    """Schema for timeline items in dashboard responses."""
    
    id: str = Field(..., description="Unique identifier for the timeline item")
    project_id: str = Field(..., description="ID of the associated project")
    project_name: str = Field(..., description="Name of the associated project")
    deliverable_id: Optional[str] = Field(None, description="ID of the associated deliverable")
    deliverable_name: Optional[str] = Field(None, description="Name of the associated deliverable")
    event_type: str = Field(..., description="Type of event: project_start, project_end, deliverable_due, milestone")
    event_date: datetime = Field(..., description="Date/time when the event occurs or occurred")
    status: str = Field(..., description="Current status of the event")
    description: Optional[str] = Field(None, description="Additional description of the timeline event")


class RecentCommentItem(BaseModel):
    """Schema for recent comment items in dashboard responses."""
    
    id: str = Field(..., description="Unique identifier for the comment")
    project_id: str = Field(..., description="ID of the associated project")
    project_name: str = Field(..., description="Name of the associated project")
    deliverable_id: str = Field(..., description="ID of the associated deliverable")
    deliverable_name: str = Field(..., description="Name of the associated deliverable")
    comment_text: str = Field(..., description="Text content of the comment")
    created_at: datetime = Field(..., description="Timestamp when comment was created")
    user_name: Optional[str] = Field(None, description="Name of the user who made the comment")
    context_coordinates: Optional[str] = Field(None, description="Coordinates if comment is tied to specific media location")
    timestamp_seconds: Optional[float] = Field(None, description="Video timestamp if comment is on video content")
    review_item_id: Optional[str] = Field(None, description="ID of the review item the comment belongs to")


class ProjectSummary(BaseModel):
    """Schema for project summary in dashboard responses."""
    
    id: str = Field(..., description="Project ID")
    name: str = Field(..., description="Project name")
    status: str = Field(..., description="Current project status")
    budget: Optional[float] = Field(None, description="Project budget")
    start_date: Optional[datetime] = Field(None, description="Project start date")
    end_date: Optional[datetime] = Field(None, description="Project end date")
    created_at: datetime = Field(..., description="Project creation timestamp")


class DashboardResponse(BaseModel):
    """Schema for main dashboard response containing KPIs, recent activity, and project summaries."""
    
    kpis: List[KPIItem] = Field(..., description="List of KPI metrics for the dashboard")
    recent_comments: List[RecentCommentItem] = Field(..., description="List of recent comments across all projects")
    timeline: List[TimelineItem] = Field(..., description="List of upcoming/recent timeline events")
    projects: List[ProjectSummary] = Field(..., description="List of accessible projects")
    

class ProjectDashboardResponse(BaseModel):
    """Schema for project-specific dashboard response."""
    
    project: ProjectSummary = Field(..., description="Project details")
    kpis: List[KPIItem] = Field(..., description="Project-specific KPI metrics")
    recent_comments: List[RecentCommentItem] = Field(..., description="Recent comments for this project")
    timeline: List[TimelineItem] = Field(..., description="Timeline events for this project") 