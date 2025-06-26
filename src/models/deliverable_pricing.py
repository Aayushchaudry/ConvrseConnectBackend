# src/models/deliverable_pricing.py

import uuid
from sqlalchemy import Column, DateTime, ForeignKey, Boolean, DECIMAL, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from src.config.database import Base


class DeliverablePricing(Base):
    """
    SQLAlchemy model for the 'deliverable_pricing' table.
    Stores pricing information for each deliverable in a project (BOQ - Bill of Quantities).
    """

    __tablename__ = "deliverable_pricing"
    __table_args__ = {"schema": "connect_backend"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign Keys
    project_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("connect_backend.projects.id"), 
        nullable=False,
        index=True
    )
    deliverable_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("connect_backend.deliverables.id"), 
        nullable=False,
        index=True
    )

    # Pricing fields
    base_price = Column(DECIMAL(12, 2), nullable=False)
    markup_percentage = Column(DECIMAL(5, 2), default=0, nullable=False)
    markup_amount = Column(DECIMAL(12, 2), default=0, nullable=False)
    discount_percentage = Column(DECIMAL(5, 2), default=0, nullable=False)
    discount_amount = Column(DECIMAL(12, 2), default=0, nullable=False)
    final_price = Column(DECIMAL(12, 2), nullable=False)

    # Additional pricing information
    cost_breakdown = Column(JSONB, nullable=True)  # JSON structure for detailed line items
    is_custom_pricing = Column(Boolean, default=False, nullable=False)
    pricing_notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    project_ref = relationship(
        "Project",
        backref="deliverable_pricing",
        lazy="joined"
    )
    deliverable_ref = relationship(
        "Deliverable",
        backref="pricing_info",
        lazy="joined"
    )

    # Table arguments with schema
    __table_args__ = {"schema": "connect_backend"}

    def calculate_final_price(self):
        """Calculate final price based on base price, markup, and discount."""
        # Apply markup
        price_with_markup = self.base_price
        if self.markup_percentage > 0:
            price_with_markup += (self.base_price * self.markup_percentage / 100)
        elif self.markup_amount > 0:
            price_with_markup += self.markup_amount

        # Apply discount
        final_price = price_with_markup
        if self.discount_percentage > 0:
            final_price -= (price_with_markup * self.discount_percentage / 100)
        elif self.discount_amount > 0:
            final_price -= self.discount_amount

        return max(final_price, 0)  # Ensure price is not negative

    def __repr__(self):
        """String representation for debugging."""
        return (
            f"<DeliverablePricing(id='{self.id}', "
            f"project_id='{self.project_id}', deliverable_id='{self.deliverable_id}', "
            f"final_price='{self.final_price}')>"
        ) 