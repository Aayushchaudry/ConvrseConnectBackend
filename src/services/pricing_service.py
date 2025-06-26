# src/services/pricing_service.py

import logging
from typing import List, Optional, Dict, Any
from uuid import UUID
from decimal import Decimal
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, update
from sqlalchemy.orm import selectinload

from src.models.project import Project
from src.models.deliverable import Deliverable
from src.models.deliverable_pricing import DeliverablePricing

logger = logging.getLogger(__name__)


class PricingService:
    """
    Service layer for deliverable pricing (Bill of Quantities - BOQ) and budget management.
    Handles pricing calculations, cost tracking, and budget variance analysis.
    """

    def __init__(self, db_session: AsyncSession):
        """
        Initialize the PricingService.
        
        Args:
            db_session: An asynchronous SQLAlchemy database session.
        """
        self.db_session = db_session
        logger.info("PricingService initialized")

    async def create_deliverable_pricing(
        self,
        project_id: UUID,
        deliverable_id: UUID,
        base_price: Decimal,
        markup_percentage: Optional[Decimal] = None,
        markup_amount: Optional[Decimal] = None,
        discount_percentage: Optional[Decimal] = None,
        discount_amount: Optional[Decimal] = None,
        cost_breakdown: Optional[Dict[str, Any]] = None,
        is_custom_pricing: bool = False,
        pricing_notes: Optional[str] = None,
    ) -> DeliverablePricing:
        """
        Create pricing information for a deliverable (BOQ entry).
        
        Args:
            project_id: ID of the project
            deliverable_id: ID of the deliverable
            base_price: Base price before markup/discount
            markup_percentage: Markup as percentage (e.g., 15.0 for 15%)
            markup_amount: Fixed markup amount
            discount_percentage: Discount as percentage
            discount_amount: Fixed discount amount
            cost_breakdown: JSON object with detailed cost breakdown
            is_custom_pricing: Whether this uses custom pricing
            pricing_notes: Additional notes about pricing
            
        Returns:
            DeliverablePricing: The created pricing entry
        """
        logger.info(f"Creating pricing for deliverable {deliverable_id} in project {project_id}")

        # Validate project and deliverable exist
        await self._validate_project_deliverable(project_id, deliverable_id)

        # Check if pricing already exists
        existing_pricing = await self._get_deliverable_pricing(project_id, deliverable_id)
        if existing_pricing:
            raise ValueError(f"Pricing already exists for deliverable {deliverable_id} in project {project_id}")

        # Calculate final price
        final_price = self._calculate_final_price(
            base_price=base_price,
            markup_percentage=markup_percentage,
            markup_amount=markup_amount,
            discount_percentage=discount_percentage,
            discount_amount=discount_amount,
        )

        # Create pricing entry
        pricing = DeliverablePricing(
            project_id=project_id,
            deliverable_id=deliverable_id,
            base_price=base_price,
            markup_percentage=markup_percentage,
            markup_amount=markup_amount,
            discount_percentage=discount_percentage,
            discount_amount=discount_amount,
            final_price=final_price,
            cost_breakdown=cost_breakdown,
            is_custom_pricing=is_custom_pricing,
            pricing_notes=pricing_notes,
        )

        self.db_session.add(pricing)
        await self.db_session.commit()
        await self.db_session.refresh(pricing)

        logger.info(f"Created pricing with ID: {pricing.id}, final price: {final_price}")

        # Update project budget
        await self.recalculate_project_budget(project_id)

        return pricing

    async def update_deliverable_pricing(
        self,
        project_id: UUID,
        deliverable_id: UUID,
        base_price: Optional[Decimal] = None,
        markup_percentage: Optional[Decimal] = None,
        markup_amount: Optional[Decimal] = None,
        discount_percentage: Optional[Decimal] = None,
        discount_amount: Optional[Decimal] = None,
        cost_breakdown: Optional[Dict[str, Any]] = None,
        is_custom_pricing: Optional[bool] = None,
        pricing_notes: Optional[str] = None,
    ) -> DeliverablePricing:
        """
        Update existing deliverable pricing.
        
        Args:
            project_id: ID of the project
            deliverable_id: ID of the deliverable
            base_price: New base price (if provided)
            markup_percentage: New markup percentage (if provided)
            markup_amount: New markup amount (if provided)
            discount_percentage: New discount percentage (if provided)
            discount_amount: New discount amount (if provided)
            cost_breakdown: New cost breakdown (if provided)
            is_custom_pricing: Whether this uses custom pricing (if provided)
            pricing_notes: New pricing notes (if provided)
            
        Returns:
            DeliverablePricing: The updated pricing entry
        """
        logger.info(f"Updating pricing for deliverable {deliverable_id} in project {project_id}")

        # Get existing pricing
        pricing = await self._get_deliverable_pricing(project_id, deliverable_id)
        if not pricing:
            raise ValueError(f"No pricing found for deliverable {deliverable_id} in project {project_id}")

        # Update fields if provided
        if base_price is not None:
            pricing.base_price = base_price
        if markup_percentage is not None:
            pricing.markup_percentage = markup_percentage
        if markup_amount is not None:
            pricing.markup_amount = markup_amount
        if discount_percentage is not None:
            pricing.discount_percentage = discount_percentage
        if discount_amount is not None:
            pricing.discount_amount = discount_amount
        if cost_breakdown is not None:
            pricing.cost_breakdown = cost_breakdown
        if is_custom_pricing is not None:
            pricing.is_custom_pricing = is_custom_pricing
        if pricing_notes is not None:
            pricing.pricing_notes = pricing_notes

        # Recalculate final price
        pricing.final_price = self._calculate_final_price(
            base_price=pricing.base_price,
            markup_percentage=pricing.markup_percentage,
            markup_amount=pricing.markup_amount,
            discount_percentage=pricing.discount_percentage,
            discount_amount=pricing.discount_amount,
        )

        pricing.updated_at = datetime.utcnow()

        await self.db_session.commit()
        await self.db_session.refresh(pricing)

        logger.info(f"Updated pricing, new final price: {pricing.final_price}")

        # Update project budget
        await self.recalculate_project_budget(project_id)

        return pricing

    async def get_project_pricing(self, project_id: UUID) -> List[DeliverablePricing]:
        """
        Get all deliverable pricing for a project.
        
        Args:
            project_id: ID of the project
            
        Returns:
            List[DeliverablePricing]: List of all pricing entries for the project
        """
        logger.info(f"Getting all pricing for project {project_id}")

        result = await self.db_session.execute(
            select(DeliverablePricing)
            .filter(DeliverablePricing.project_id == project_id)
            .options(selectinload(DeliverablePricing.deliverable))
        )
        
        pricing_entries = result.scalars().all()
        logger.info(f"Found {len(pricing_entries)} pricing entries for project {project_id}")
        return pricing_entries

    async def delete_deliverable_pricing(
        self,
        project_id: UUID,
        deliverable_id: UUID,
    ) -> bool:
        """
        Remove pricing for a specific deliverable.
        
        Args:
            project_id: ID of the project
            deliverable_id: ID of the deliverable
            
        Returns:
            bool: True if pricing was removed, False if not found
        """
        logger.info(f"Removing pricing for deliverable {deliverable_id} in project {project_id}")

        pricing = await self._get_deliverable_pricing(project_id, deliverable_id)
        if not pricing:
            logger.warning(f"No pricing found for deliverable {deliverable_id} in project {project_id}")
            return False

        await self.db_session.delete(pricing)
        await self.db_session.commit()

        logger.info("Removed deliverable pricing")

        # Update project budget
        await self.recalculate_project_budget(project_id)

        return True

    async def calculate_project_budget(self, project_id: UUID) -> Decimal:
        """
        Calculate total project budget by summing all deliverable final prices.
        
        Args:
            project_id: ID of the project
            
        Returns:
            Decimal: Total calculated budget
        """
        logger.info(f"Calculating budget for project {project_id}")

        result = await self.db_session.execute(
            select(func.sum(DeliverablePricing.final_price))
            .filter(DeliverablePricing.project_id == project_id)
        )
        
        total_budget = result.scalar() or Decimal('0.00')
        logger.info(f"Calculated budget for project {project_id}: {total_budget}")
        return total_budget

    async def recalculate_project_budget(self, project_id: UUID) -> Project:
        """
        Recalculate and update the project's calculated budget.
        
        Args:
            project_id: ID of the project
            
        Returns:
            Project: Updated project with new calculated budget
        """
        logger.info(f"Recalculating project budget for {project_id}")

        # Calculate new budget
        new_budget = await self.calculate_project_budget(project_id)
        
        # Update project
        result = await self.db_session.execute(
            update(Project)
            .where(Project.id == project_id)
            .values(
                calculated_budget=new_budget,
                budget_last_calculated=datetime.utcnow(),
            )
            .returning(Project)
        )
        
        updated_project = result.scalar_one()
        await self.db_session.commit()

        logger.info(f"Updated project calculated budget to: {new_budget}")
        return updated_project

    async def track_actual_cost(
        self,
        project_id: UUID,
        cost_amount: Decimal,
        cost_description: Optional[str] = None,
    ) -> Project:
        """
        Add to the actual cost for a project and update budget variance.
        
        Args:
            project_id: ID of the project
            cost_amount: Amount to add to actual costs
            cost_description: Description of the cost (for logging)
            
        Returns:
            Project: Updated project with new actual cost and variance
        """
        logger.info(f"Tracking cost of {cost_amount} for project {project_id}: {cost_description}")

        # Get current project
        project = await self._get_project_by_id(project_id)
        if not project:
            raise ValueError(f"Project with ID {project_id} not found")

        # Update actual cost
        new_actual_cost = (project.actual_cost or Decimal('0.00')) + cost_amount
        
        # Calculate budget variance (positive = over budget, negative = under budget)
        calculated_budget = project.calculated_budget or project.budget or Decimal('0.00')
        new_variance = new_actual_cost - calculated_budget

        # Update project
        result = await self.db_session.execute(
            update(Project)
            .where(Project.id == project_id)
            .values(
                actual_cost=new_actual_cost,
                budget_variance=new_variance,
            )
            .returning(Project)
        )
        
        updated_project = result.scalar_one()
        await self.db_session.commit()

        logger.info(f"Updated actual cost to {new_actual_cost}, variance: {new_variance}")
        return updated_project

    async def get_cost_breakdown(self, project_id: UUID) -> Dict[str, Any]:
        """
        Get detailed cost analysis for a project.
        
        Args:
            project_id: ID of the project
            
        Returns:
            Dict containing detailed cost breakdown and analysis
        """
        logger.info(f"Getting cost breakdown for project {project_id}")

        # Get project
        project = await self._get_project_by_id(project_id)
        if not project:
            raise ValueError(f"Project with ID {project_id} not found")

        # Get all pricing entries
        pricing_entries = await self.get_project_pricing(project_id)

        # Calculate totals
        total_base_price = sum(p.base_price for p in pricing_entries)
        total_markup = sum((p.markup_amount or Decimal('0.00')) for p in pricing_entries)
        total_discount = sum((p.discount_amount or Decimal('0.00')) for p in pricing_entries)
        calculated_budget = project.calculated_budget or Decimal('0.00')
        actual_cost = project.actual_cost or Decimal('0.00')
        budget_variance = project.budget_variance or Decimal('0.00')

        # Build detailed breakdown
        deliverable_breakdown = []
        for pricing in pricing_entries:
            deliverable_info = {
                "deliverable_id": str(pricing.deliverable_id),
                "deliverable_type": pricing.deliverable.deliverable_type if pricing.deliverable else "Unknown",
                "base_price": float(pricing.base_price),
                "markup_percentage": float(pricing.markup_percentage or 0),
                "markup_amount": float(pricing.markup_amount or 0),
                "discount_percentage": float(pricing.discount_percentage or 0),
                "discount_amount": float(pricing.discount_amount or 0),
                "final_price": float(pricing.final_price),
                "is_custom_pricing": pricing.is_custom_pricing,
                "cost_breakdown": pricing.cost_breakdown,
            }
            deliverable_breakdown.append(deliverable_info)

        cost_analysis = {
            "project_id": str(project_id),
            "summary": {
                "total_base_price": float(total_base_price),
                "total_markup": float(total_markup),
                "total_discount": float(total_discount),
                "calculated_budget": float(calculated_budget),
                "original_budget": float(project.budget or 0),
                "actual_cost": float(actual_cost),
                "budget_variance": float(budget_variance),
                "variance_percentage": float((budget_variance / calculated_budget * 100) if calculated_budget > 0 else 0),
                "cost_overrun": budget_variance > 0,
            },
            "deliverable_breakdown": deliverable_breakdown,
            "analysis": {
                "is_over_budget": budget_variance > 0,
                "is_under_budget": budget_variance < 0,
                "budget_utilization_percentage": float((actual_cost / calculated_budget * 100) if calculated_budget > 0 else 0),
                "remaining_budget": float(calculated_budget - actual_cost),
            }
        }

        logger.info(f"Generated cost breakdown - Budget: {calculated_budget}, Actual: {actual_cost}, Variance: {budget_variance}")
        return cost_analysis

    # Helper methods

    def _calculate_final_price(
        self,
        base_price: Decimal,
        markup_percentage: Optional[Decimal] = None,
        markup_amount: Optional[Decimal] = None,
        discount_percentage: Optional[Decimal] = None,
        discount_amount: Optional[Decimal] = None,
    ) -> Decimal:
        """
        Calculate final price with markup and discount.
        
        Args:
            base_price: Base price
            markup_percentage: Markup as percentage
            markup_amount: Fixed markup amount
            discount_percentage: Discount as percentage
            discount_amount: Fixed discount amount
            
        Returns:
            Decimal: Final calculated price
        """
        final_price = base_price

        # Apply markup
        if markup_percentage is not None and markup_percentage > 0:
            markup = base_price * (markup_percentage / Decimal('100'))
            final_price += markup
        elif markup_amount is not None and markup_amount > 0:
            final_price += markup_amount

        # Apply discount
        if discount_percentage is not None and discount_percentage > 0:
            discount = final_price * (discount_percentage / Decimal('100'))
            final_price -= discount
        elif discount_amount is not None and discount_amount > 0:
            final_price -= discount_amount

        # Ensure final price is not negative
        return max(final_price, Decimal('0.00'))

    async def _validate_project_deliverable(self, project_id: UUID, deliverable_id: UUID) -> None:
        """Validate that project and deliverable exist and are related."""
        deliverable = await self.db_session.execute(
            select(Deliverable).filter(Deliverable.id == deliverable_id)
        )
        deliverable = deliverable.scalar_one_or_none()
        
        if not deliverable:
            raise ValueError(f"Deliverable with ID {deliverable_id} not found")
        
        if deliverable.project_id != project_id:
            raise ValueError(f"Deliverable {deliverable_id} does not belong to project {project_id}")

    async def _get_deliverable_pricing(
        self, project_id: UUID, deliverable_id: UUID
    ) -> Optional[DeliverablePricing]:
        """Get existing pricing for a deliverable."""
        result = await self.db_session.execute(
            select(DeliverablePricing).filter(
                and_(
                    DeliverablePricing.project_id == project_id,
                    DeliverablePricing.deliverable_id == deliverable_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def _get_project_by_id(self, project_id: UUID) -> Optional[Project]:
        """Get project by ID."""
        result = await self.db_session.execute(
            select(Project).filter(Project.id == project_id)
        )
        return result.scalar_one_or_none() 