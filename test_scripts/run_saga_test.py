#!/usr/bin/env python3

import asyncio
import sys
import os
from datetime import datetime
from sqlalchemy import select

# Add the src directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.config.database import AsyncSessionLocal
from src.config.event_bus import get_event_bus, close_event_bus
from src.models.project import Project
from src.models.deliverable import Deliverable, DeliverableStatus
from src.models.review_item import ReviewItem, ReviewItemType, ReviewStatus
from src.models.internal_task import InternalTask, TaskStatus
from src.models.client_feedback import ClientFeedback, FeedbackType
from src.models.saga_state import SagaState

# Import events and commands
from src.events.project_events import ProjectCreatedEvent
from src.events.deliverable_events import DeliverableInfoGatheredEvent
from src.events.client_feedback_events import ClientFeedbackSubmittedEvent, ReviewItemApprovedEvent
from src.commands.project_commands import StartInformationGatheringCommand

class SagaFlowTest:
    def __init__(self):
        self.project_id = "8106f10b-46e6-496d-898f-9d826cc8ee0d"  # Existing project
        self.deliverable_id = "6d4d1663-bd14-4976-ba9d-2cad4de878cd"  # Existing deliverable
        self.event_bus = None
        
    def log(self, message):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        
    async def setup_event_bus(self):
        """Initialize the event bus for testing"""
        self.log("Setting up event bus...")
        try:
            self.event_bus = await get_event_bus()
            self.log("✅ Event bus initialized successfully")
            return True
        except Exception as e:
            self.log(f"❌ Failed to initialize event bus: {e}")
            return False
            
    async def cleanup_event_bus(self):
        """Clean up the event bus"""
        if self.event_bus:
            await close_event_bus()
            self.log("✅ Event bus closed")

    async def verify_and_trigger_saga(self):
        """Verify project/deliverable exist and trigger SAGA flow"""
        self.log("Step 1: Verifying entities and triggering SAGA...")
        
        try:
            async with AsyncSessionLocal() as session:
                # Verify Project exists
                project_result = await session.execute(
                    select(Project).where(Project.id == self.project_id)
                )
                project = project_result.scalar_one_or_none()
                if not project:
                    self.log("❌ Project not found!")
                    return False
                self.log(f"✅ Found project: {project.name}")

                # Verify Deliverable exists
                deliverable_result = await session.execute(
                    select(Deliverable).where(Deliverable.id == self.deliverable_id)
                )
                deliverable = deliverable_result.scalar_one_or_none()
                if not deliverable:
                    self.log("❌ Deliverable not found!")
                    return False
                self.log(f"✅ Found deliverable: {deliverable.deliverable_type}")

                # Publish ProjectCreatedEvent to trigger SAGA
                project_created_event = ProjectCreatedEvent(
                    project_id=self.project_id,
                    project_name=project.name,
                    initial_status=project.status.value
                )
                await self.event_bus.publish(
                    topic="project.created",
                    message=project_created_event.__dict__
                )
                self.log("✅ ProjectCreatedEvent published")

                # Publish StartInformationGatheringCommand
                start_info_command = StartInformationGatheringCommand(
                    project_id=self.project_id,
                    deliverable_ids=[self.deliverable_id]
                )
                await self.event_bus.publish(
                    topic="project.command.start_info_gathering",
                    message=start_info_command.__dict__
                )
                self.log("✅ StartInformationGatheringCommand published")

                # Simulate info gathering completion
                info_gathered_event = DeliverableInfoGatheredEvent(
                    project_id=self.project_id,
                    deliverable_id=self.deliverable_id
                )
                await self.event_bus.publish(
                    topic="deliverable.info_gathered",
                    message=info_gathered_event.__dict__
                )
                self.log("✅ DeliverableInfoGatheredEvent published")

                return True

        except Exception as e:
            self.log(f"❌ Error in verify_and_trigger_saga: {e}")
            return False

    async def submit_client_approval(self):
        """Submit client approval to move the SAGA forward"""
        self.log("Step 2: Submitting client approval...")
        
        try:
            async with AsyncSessionLocal() as session:
                # Find the latest review item
                review_result = await session.execute(
                    select(ReviewItem).where(
                        ReviewItem.deliverable_id == self.deliverable_id
                    ).order_by(ReviewItem.created_at.desc())
                )
                review_item = review_result.scalar_one_or_none()
                
                if not review_item:
                    self.log("❌ No review item found!")
                    return False
                
                self.log(f"✅ Found review item: {review_item.id}")

                # Submit client feedback
                feedback_event = ClientFeedbackSubmittedEvent(
                    project_id=self.project_id,
                    deliverable_id=self.deliverable_id,
                    review_item_id=str(review_item.id),
                    feedback_type=FeedbackType.ACCEPT.value,
                    client_user_id="test-user-id",
                    comment_text="Approved for final delivery"
                )
                await self.event_bus.publish(
                    topic="client.feedback.submitted",
                    message=feedback_event.__dict__
                )
                self.log("✅ ClientFeedbackSubmittedEvent published")

                # Also publish ReviewItemApprovedEvent
                approved_event = ReviewItemApprovedEvent(
                    project_id=self.project_id,
                    deliverable_id=self.deliverable_id,
                    review_item_id=str(review_item.id),
                    approved_by_user_id="test-user-id"
                )
                await self.event_bus.publish(
                    topic="deliverable.review_item.approved",
                    message=approved_event.__dict__
                )
                self.log("✅ ReviewItemApprovedEvent published")

                return True

        except Exception as e:
            self.log(f"❌ Error in submit_client_approval: {e}")
            return False

    async def verify_saga_completion(self):
        """Verify the SAGA completed successfully"""
        self.log("Step 3: Verifying SAGA completion...")
        
        try:
            async with AsyncSessionLocal() as session:
                # Check SAGA states
                saga_result = await session.execute(
                    select(SagaState).where(
                        SagaState.project_id == self.project_id
                    )
                )
                saga_states = saga_result.scalars().all()
                
                if not saga_states:
                    self.log("❌ No SAGA states found!")
                    return False
                
                self.log(f"Found {len(saga_states)} SAGA state(s):")
                for saga in saga_states:
                    self.log(f"   - Type: {saga.saga_type.value}")
                    self.log(f"   - State: {saga.current_state}")
                    self.log(f"   - Status: {saga.status.value}")

                # Check deliverable status
                deliverable_result = await session.execute(
                    select(Deliverable).where(
                        Deliverable.id == self.deliverable_id
                    )
                )
                deliverable = deliverable_result.scalar_one()
                self.log(f"Deliverable status: {deliverable.current_status.value}")

                return True

        except Exception as e:
            self.log(f"❌ Error in verify_saga_completion: {e}")
            return False

    async def run_saga_test(self):
        """Run the complete SAGA test"""
        try:
            # Setup
            if not await self.setup_event_bus():
                return False
                
            # Run test steps
            if not await self.verify_and_trigger_saga():
                return False
                
            self.log("Waiting for initial processing...")
            await asyncio.sleep(5)
                
            if not await self.submit_client_approval():
                return False
                
            self.log("Waiting for final processing...")
            await asyncio.sleep(5)
                
            if not await self.verify_saga_completion():
                return False
                
            self.log("✅ SAGA test completed successfully!")
            return True
            
        except Exception as e:
            self.log(f"❌ Error in run_saga_test: {e}")
            return False
            
        finally:
            await self.cleanup_event_bus()

async def main():
    test = SagaFlowTest()
    await test.run_saga_test()

if __name__ == "__main__":
    asyncio.run(main()) 