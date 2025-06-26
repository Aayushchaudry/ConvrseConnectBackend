# src/api/pricing/controllers.py

from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db_session
from src.middleware.auth_middleware import AuthContext, require_auth
from src.services.pricing_service import PricingService

import logging
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/pricing",
    tags=["Pricing Management"],
    redirect_slashes=False,
)


# --- Request/Response Models ---

class DeliverablePricingRequest(BaseModel):
    """Request model for setting deliverable pricing."""
    
    deliverable_id: UUID = Field(..., description="Deliverable ID to set pricing for")
    base_price: float = Field(..., gt=0, description="Base price for the deliverable")
    markup_percentage: Optional[float] = Field(None, ge=0, description="Markup percentage (0-100)")
    markup_amount: Optional[float] = Field(None, ge=0, description="Fixed markup amount")
    discount_percentage: Optional[float] = Field(None, ge=0, le=100, description="Discount percentage (0-100)")
    discount_amount: Optional[float] = Field(None, ge=0, description="Fixed discount amount")
    cost_breakdown: Optional[Dict[str, Any]] = Field(None, description="Detailed cost breakdown")
    is_custom_pricing: bool = Field(False, description="Whether this is custom pricing")
    pricing_notes: Optional[str] = Field(None, max_length=1000, description="Additional pricing notes")


class DeliverablePricingResponse(BaseModel):
    """Response model for deliverable pricing data."""
    
    id: UUID
    project_id: UUID
    deliverable_id: UUID
    base_price: float
    markup_percentage: Optional[float]
    markup_amount: Optional[float]
    discount_percentage: Optional[float]
    discount_amount: Optional[float]
    final_price: float
    cost_breakdown: Optional[Dict[str, Any]]
    is_custom_pricing: bool
    pricing_notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ProjectBudgetSummaryResponse(BaseModel):
    """Response model for project budget summary."""
    
    project_id: UUID
    total_base_price: float
    total_markup: float
    total_discount: float
    calculated_budget: float
    actual_cost: float
    budget_variance: float
    budget_utilization_percentage: float
    last_calculated: datetime
    deliverable_pricing: List[DeliverablePricingResponse]


class CostAnalysisResponse(BaseModel):
    """Response model for cost analysis."""
    
    project_id: UUID
    budget_analysis: Dict[str, Any]
    cost_breakdown_by_deliverable: List[Dict[str, Any]]
    variance_analysis: Dict[str, Any]
    budget_alerts: List[Dict[str, Any]]


class BudgetRecalculationRequest(BaseModel):
    """Request model for budget recalculation."""
    
    force_recalculate: bool = Field(False, description="Force recalculation even if recently calculated")


class ActualCostRequest(BaseModel):
    """Request model for tracking actual costs."""
    
    deliverable_id: UUID = Field(..., description="Deliverable ID")
    actual_cost: float = Field(..., gt=0, description="Actual cost incurred")
    cost_category: str = Field(..., description="Category of the cost")
    cost_description: Optional[str] = Field(None, max_length=500, description="Description of the cost")


# --- API Endpoints ---

@router.post("/projects/{project_id}/pricing", response_model=DeliverablePricingResponse, status_code=status.HTTP_201_CREATED)
async def set_deliverable_pricing(
    project_id: UUID,
    pricing_data: DeliverablePricingRequest,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Set pricing for a deliverable in a project.
    """
    auth_context = require_auth(request)
    
    try:
        pricing_service = PricingService(db_session)
        
        # Create deliverable pricing
        pricing = await pricing_service.create_deliverable_pricing(
            project_id=project_id,
            deliverable_id=pricing_data.deliverable_id,
            base_price=Decimal(str(pricing_data.base_price)),
            markup_percentage=Decimal(str(pricing_data.markup_percentage)) if pricing_data.markup_percentage else None,
            markup_amount=Decimal(str(pricing_data.markup_amount)) if pricing_data.markup_amount else None,
            discount_percentage=Decimal(str(pricing_data.discount_percentage)) if pricing_data.discount_percentage else None,
            discount_amount=Decimal(str(pricing_data.discount_amount)) if pricing_data.discount_amount else None,
            cost_breakdown=pricing_data.cost_breakdown,
            is_custom_pricing=pricing_data.is_custom_pricing,
            pricing_notes=pricing_data.pricing_notes,
        )
        
        return DeliverablePricingResponse(
            id=pricing.id,
            project_id=pricing.project_id,
            deliverable_id=pricing.deliverable_id,
            base_price=float(pricing.base_price),
            markup_percentage=float(pricing.markup_percentage) if pricing.markup_percentage else None,
            markup_amount=float(pricing.markup_amount) if pricing.markup_amount else None,
            discount_percentage=float(pricing.discount_percentage) if pricing.discount_percentage else None,
            discount_amount=float(pricing.discount_amount) if pricing.discount_amount else None,
            final_price=float(pricing.final_price),
            cost_breakdown=pricing.cost_breakdown,
            is_custom_pricing=pricing.is_custom_pricing,
            pricing_notes=pricing.pricing_notes,
            created_at=pricing.created_at,
            updated_at=pricing.updated_at,
        )
        
    except ValueError as ve:
        logger.error(f"Validation error setting deliverable pricing: {ve}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve),
        )
    except Exception as e:
        logger.error(f"Error setting deliverable pricing: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to set deliverable pricing: {str(e)}",
        )


@router.put("/projects/{project_id}/deliverables/{deliverable_id}/pricing", response_model=DeliverablePricingResponse)
async def update_deliverable_pricing(
    project_id: UUID,
    deliverable_id: UUID,
    pricing_data: DeliverablePricingRequest,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Update pricing for a specific deliverable.
    """
    auth_context = require_auth(request)
    
    try:
        pricing_service = PricingService(db_session)
        
        # Update deliverable pricing
        pricing = await pricing_service.update_deliverable_pricing(
            project_id=project_id,
            deliverable_id=deliverable_id,
            base_price=Decimal(str(pricing_data.base_price)),
            markup_percentage=Decimal(str(pricing_data.markup_percentage)) if pricing_data.markup_percentage else None,
            markup_amount=Decimal(str(pricing_data.markup_amount)) if pricing_data.markup_amount else None,
            discount_percentage=Decimal(str(pricing_data.discount_percentage)) if pricing_data.discount_percentage else None,
            discount_amount=Decimal(str(pricing_data.discount_amount)) if pricing_data.discount_amount else None,
            cost_breakdown=pricing_data.cost_breakdown,
            is_custom_pricing=pricing_data.is_custom_pricing,
            pricing_notes=pricing_data.pricing_notes,
        )
        
        if not pricing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Deliverable pricing not found",
            )
        
        return DeliverablePricingResponse(
            id=pricing.id,
            project_id=pricing.project_id,
            deliverable_id=pricing.deliverable_id,
            base_price=float(pricing.base_price),
            markup_percentage=float(pricing.markup_percentage) if pricing.markup_percentage else None,
            markup_amount=float(pricing.markup_amount) if pricing.markup_amount else None,
            discount_percentage=float(pricing.discount_percentage) if pricing.discount_percentage else None,
            discount_amount=float(pricing.discount_amount) if pricing.discount_amount else None,
            final_price=float(pricing.final_price),
            cost_breakdown=pricing.cost_breakdown,
            is_custom_pricing=pricing.is_custom_pricing,
            pricing_notes=pricing.pricing_notes,
            created_at=pricing.created_at,
            updated_at=pricing.updated_at,
        )
        
    except ValueError as ve:
        logger.error(f"Validation error updating deliverable pricing: {ve}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating deliverable pricing: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update deliverable pricing: {str(e)}",
        )


@router.get("/projects/{project_id}/pricing", response_model=List[DeliverablePricingResponse])
async def get_project_pricing(
    project_id: UUID,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Get all deliverable pricing for a project.
    """
    auth_context = require_auth(request)
    
    try:
        from sqlalchemy import select
        from src.models.deliverable_pricing import DeliverablePricing
        
        result = await db_session.execute(
            select(DeliverablePricing).filter(DeliverablePricing.project_id == project_id)
        )
        pricing_records = result.scalars().all()
        
        return [
            DeliverablePricingResponse(
                id=pricing.id,
                project_id=pricing.project_id,
                deliverable_id=pricing.deliverable_id,
                base_price=float(pricing.base_price),
                markup_percentage=float(pricing.markup_percentage) if pricing.markup_percentage else None,
                markup_amount=float(pricing.markup_amount) if pricing.markup_amount else None,
                discount_percentage=float(pricing.discount_percentage) if pricing.discount_percentage else None,
                discount_amount=float(pricing.discount_amount) if pricing.discount_amount else None,
                final_price=float(pricing.final_price),
                cost_breakdown=pricing.cost_breakdown,
                is_custom_pricing=pricing.is_custom_pricing,
                pricing_notes=pricing.pricing_notes,
                created_at=pricing.created_at,
                updated_at=pricing.updated_at,
            )
            for pricing in pricing_records
        ]
        
    except Exception as e:
        logger.error(f"Error fetching project pricing: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch project pricing: {str(e)}",
        )


@router.delete("/projects/{project_id}/deliverables/{deliverable_id}/pricing", status_code=status.HTTP_204_NO_CONTENT)
async def remove_deliverable_pricing(
    project_id: UUID,
    deliverable_id: UUID,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Remove pricing for a specific deliverable.
    """
    auth_context = require_auth(request)
    
    try:
        from sqlalchemy import select, delete
        from src.models.deliverable_pricing import DeliverablePricing
        
        # Check if pricing exists
        result = await db_session.execute(
            select(DeliverablePricing).filter(
                DeliverablePricing.project_id == project_id,
                DeliverablePricing.deliverable_id == deliverable_id
            )
        )
        pricing = result.scalar_one_or_none()
        
        if not pricing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Deliverable pricing not found",
            )
        
        # Delete pricing
        await db_session.execute(
            delete(DeliverablePricing).filter(
                DeliverablePricing.project_id == project_id,
                DeliverablePricing.deliverable_id == deliverable_id
            )
        )
        await db_session.commit()
        
        # Recalculate project budget
        pricing_service = PricingService(db_session)
        await pricing_service.recalculate_project_budget(project_id)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing deliverable pricing: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove deliverable pricing: {str(e)}",
        )


@router.get("/projects/{project_id}/budget-summary", response_model=ProjectBudgetSummaryResponse)
async def get_project_budget_summary(
    project_id: UUID,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Get detailed budget breakdown for a project.
    """
    auth_context = require_auth(request)
    
    try:
        pricing_service = PricingService(db_session)
        
        # Calculate project budget
        budget_info = await pricing_service.calculate_project_budget(project_id)
        
        # Get all deliverable pricing for the project
        from sqlalchemy import select
        from src.models.deliverable_pricing import DeliverablePricing
        
        result = await db_session.execute(
            select(DeliverablePricing).filter(DeliverablePricing.project_id == project_id)
        )
        pricing_records = result.scalars().all()
        
        deliverable_pricing = [
            DeliverablePricingResponse(
                id=pricing.id,
                project_id=pricing.project_id,
                deliverable_id=pricing.deliverable_id,
                base_price=float(pricing.base_price),
                markup_percentage=float(pricing.markup_percentage) if pricing.markup_percentage else None,
                markup_amount=float(pricing.markup_amount) if pricing.markup_amount else None,
                discount_percentage=float(pricing.discount_percentage) if pricing.discount_percentage else None,
                discount_amount=float(pricing.discount_amount) if pricing.discount_amount else None,
                final_price=float(pricing.final_price),
                cost_breakdown=pricing.cost_breakdown,
                is_custom_pricing=pricing.is_custom_pricing,
                pricing_notes=pricing.pricing_notes,
                created_at=pricing.created_at,
                updated_at=pricing.updated_at,
            )
            for pricing in pricing_records
        ]
        
        return ProjectBudgetSummaryResponse(
            project_id=project_id,
            total_base_price=float(budget_info["total_base_price"]),
            total_markup=float(budget_info["total_markup"]),
            total_discount=float(budget_info["total_discount"]),
            calculated_budget=float(budget_info["calculated_budget"]),
            actual_cost=float(budget_info["actual_cost"]),
            budget_variance=float(budget_info["budget_variance"]),
            budget_utilization_percentage=float(budget_info["budget_utilization_percentage"]),
            last_calculated=budget_info["last_calculated"],
            deliverable_pricing=deliverable_pricing,
        )
        
    except Exception as e:
        logger.error(f"Error fetching budget summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch budget summary: {str(e)}",
        )


@router.post("/projects/{project_id}/calculate-budget", response_model=Dict[str, Any])
async def recalculate_project_budget(
    project_id: UUID,
    recalc_data: BudgetRecalculationRequest,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Recalculate project budget.
    """
    auth_context = require_auth(request)
    
    try:
        pricing_service = PricingService(db_session)
        
        budget_info = await pricing_service.recalculate_project_budget(
            project_id=project_id,
            force_recalculate=recalc_data.force_recalculate,
        )
        
        return {
            "project_id": str(project_id),
            "budget_recalculated": True,
            "calculated_budget": float(budget_info["calculated_budget"]),
            "last_calculated": budget_info["last_calculated"].isoformat(),
            "budget_breakdown": budget_info,
        }
        
    except Exception as e:
        logger.error(f"Error recalculating budget: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to recalculate budget: {str(e)}",
        )


@router.get("/projects/{project_id}/cost-analysis", response_model=CostAnalysisResponse)
async def get_cost_analysis(
    project_id: UUID,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Get detailed cost vs budget analysis for a project.
    """
    auth_context = require_auth(request)
    
    try:
        pricing_service = PricingService(db_session)
        
        # Get cost breakdown
        cost_breakdown = await pricing_service.get_cost_breakdown(project_id)
        
        return CostAnalysisResponse(
            project_id=project_id,
            budget_analysis=cost_breakdown["budget_analysis"],
            cost_breakdown_by_deliverable=cost_breakdown["cost_breakdown_by_deliverable"],
            variance_analysis=cost_breakdown["variance_analysis"],
            budget_alerts=cost_breakdown.get("budget_alerts", []),
        )
        
    except Exception as e:
        logger.error(f"Error fetching cost analysis: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch cost analysis: {str(e)}",
        )


@router.post("/projects/{project_id}/track-cost", response_model=Dict[str, Any])
async def track_actual_cost(
    project_id: UUID,
    cost_data: ActualCostRequest,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Track actual costs for a deliverable.
    """
    auth_context = require_auth(request)
    
    try:
        pricing_service = PricingService(db_session)
        
        # Track actual cost
        result = await pricing_service.track_actual_cost(
            project_id=project_id,
            deliverable_id=cost_data.deliverable_id,
            actual_cost=Decimal(str(cost_data.actual_cost)),
            cost_category=cost_data.cost_category,
            cost_description=cost_data.cost_description,
        )
        
        return {
            "project_id": str(project_id),
            "deliverable_id": str(cost_data.deliverable_id),
            "cost_tracked": True,
            "actual_cost": float(cost_data.actual_cost),
            "total_actual_cost": float(result["total_actual_cost"]),
            "budget_variance": float(result["budget_variance"]),
            "budget_utilization_percentage": float(result["budget_utilization_percentage"]),
        }
        
    except ValueError as ve:
        logger.error(f"Validation error tracking actual cost: {ve}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve),
        )
    except Exception as e:
        logger.error(f"Error tracking actual cost: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to track actual cost: {str(e)}",
        ) 