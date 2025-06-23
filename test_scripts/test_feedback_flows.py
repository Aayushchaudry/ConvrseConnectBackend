#!/usr/bin/env python3

import asyncio
import uuid
from datetime import datetime
import sys
import os
from sqlalchemy import select, delete

# Add the src directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.config.database import AsyncSessionLocal
from src.config.event_bus import get_event_bus, close_event_bus
from src.models.project import Project
from src.models.deliverable import Deliverable, DeliverableType, DeliverableStatus
from src.models.review_item import ReviewItem, ReviewItemType, ReviewStatus
from src.models.internal_task import InternalTask, TaskStatus, TaskType, Priority
from src.models.client_feedback import ClientFeedback, FeedbackType
from src.models.saga_state import SagaState, SagaType, SagaStatus

from src.events.client_feedback_events import ClientFeedbackSubmittedEvent
from src.orchestrators.deliverable_saga_orchestrator.deliverable_saga_orchestrator import DeliverableSagaOrchestrator

class TestFeedbackFlows:
    def __init__(self):
        self.project_id = str(uuid.uuid4())
        self.deliverable_id = str(uuid.uuid4())
        self.review_item_id = str(uuid.uuid4())
        self.event_bus = None
        self.deliverable_orchestrator = None

    def log(self, message):
        """Helper to print logs with timestamps"""
        print(f"[{datetime.now().isoformat()}] {message}")

    async def setup(self):
        """Set up test environment"""
        self.log("Setting up test environment...")
        self.event_bus = await get_event_bus()
        
        # Create DeliverableSagaOrchestrator instance
        self.deliverable_orchestrator = DeliverableSagaOrchestrator(
            db_session_factory=AsyncSessionLocal,
            event_bus=self.event_bus
        )

        async with AsyncSessionLocal() as session:
            # Create test project
            project = Project(
                id=self.project_id,
                name="Feedback Flow Test Project",
                status="active"
            )
            session.add(project)

            # Create test deliverable
            deliverable = Deliverable(
                id=self.deliverable_id,
                project_id=self.project_id,
                deliverable_type=DeliverableType.MODERN_RESTAURANT,
                status=DeliverableStatus.IN_REVIEW
            )
            session.add(deliverable)

            # Create test review item
            review_item = ReviewItem(
                id=self.review_item_id,
                project_id=self.project_id,
                deliverable_id=self.deliverable_id,
                review_type=ReviewItemType.STATIC_RENDER,
                review_status=ReviewStatus.PENDING_REVIEW,
                asset_url="http://example.com/test.jpg"
            )
            session.add(review_item)

            await session.commit()
            self.log("✅ Test environment setup complete")

    async def test_comment_feedback(self):
        """Test comment feedback flow"""
        self.log("\nTesting comment feedback flow...")
        
        feedback_id = str(uuid.uuid4())
        
        try:
            async with AsyncSessionLocal() as session:
                # Create Client Feedback
                feedback = ClientFeedback(
                    id=feedback_id,
                    review_item_id=self.review_item_id,
                    project_id=self.project_id,
                    deliverable_id=self.deliverable_id,
                    feedback_type=FeedbackType.COMMENT,
                    comment_text="Please adjust the lighting in the corner."
                )
                session.add(feedback)
                await session.commit()
                self.log("✅ Comment feedback created")

                # Create and submit feedback event
                feedback_event = ClientFeedbackSubmittedEvent(
                    project_id=self.project_id,
                    deliverable_id=self.deliverable_id,
                    review_item_id=self.review_item_id,
                    client_user_id=None,
                    feedback_type="comment",
                    comment_text="Please adjust the lighting in the corner."
                )

                # Process the feedback through orchestrator
                await self.deliverable_orchestrator.on_client_feedback_submitted(feedback_event)
                self.log("✅ Comment feedback processed by orchestrator")

                # Verify rework task was created
                await asyncio.sleep(1)  # Give time for async operations
                rework_task_result = await session.execute(
                    select(InternalTask).where(
                        InternalTask.deliverable_id == self.deliverable_id,
                        InternalTask.task_type == TaskType.REWORK
                    )
                )
                rework_task = rework_task_result.scalar_one_or_none()
                
                if rework_task:
                    self.log(f"✅ Rework task created successfully: {rework_task.id}")
                    self.log(f"   Task Name: {rework_task.task_name}")
                    self.log(f"   Description: {rework_task.description}")
                else:
                    self.log("❌ No rework task was created!")
                    return False

                # Verify SAGA state
                saga_state_result = await session.execute(
                    select(SagaState).where(
                        SagaState.deliverable_id == self.deliverable_id,
                        SagaState.saga_type == SagaType.DELIVERABLE_PRODUCTION
                    )
                )
                saga_state = saga_state_result.scalar_one_or_none()
                
                if saga_state and saga_state.current_state == "REVISIONS_IN_PROGRESS":
                    self.log("✅ SAGA state correctly updated to REVISIONS_IN_PROGRESS")
                else:
                    self.log("❌ SAGA state not updated correctly!")
                    return False

                return True

        except Exception as e:
            self.log(f"❌ Error in comment feedback test: {str(e)}")
            return False

    async def test_reject_feedback(self):
        """Test reject feedback flow"""
        self.log("\nTesting reject feedback flow...")
        
        feedback_id = str(uuid.uuid4())
        
        try:
            async with AsyncSessionLocal() as session:
                # Create Client Feedback
                feedback = ClientFeedback(
                    id=feedback_id,
                    review_item_id=self.review_item_id,
                    project_id=self.project_id,
                    deliverable_id=self.deliverable_id,
                    feedback_type=FeedbackType.REJECT,
                    comment_text="The design needs a complete revision."
                )
                session.add(feedback)
                await session.commit()
                self.log("✅ Reject feedback created")

                # Create and submit feedback event
                feedback_event = ClientFeedbackSubmittedEvent(
                    project_id=self.project_id,
                    deliverable_id=self.deliverable_id,
                    review_item_id=self.review_item_id,
                    client_user_id=None,
                    feedback_type="reject",
                    comment_text="The design needs a complete revision."
                )

                # Process the feedback through orchestrator
                await self.deliverable_orchestrator.on_client_feedback_submitted(feedback_event)
                self.log("✅ Reject feedback processed by orchestrator")

                # Verify rework task was created
                await asyncio.sleep(1)  # Give time for async operations
                rework_task_result = await session.execute(
                    select(InternalTask).where(
                        InternalTask.deliverable_id == self.deliverable_id,
                        InternalTask.task_type == TaskType.REWORK
                    )
                )
                rework_task = rework_task_result.scalar_one_or_none()
                
                if rework_task:
                    self.log(f"✅ Rework task created successfully: {rework_task.id}")
                    self.log(f"   Task Name: {rework_task.task_name}")
                    self.log(f"   Description: {rework_task.description}")
                else:
                    self.log("❌ No rework task was created!")
                    return False

                # Verify SAGA state
                saga_state_result = await session.execute(
                    select(SagaState).where(
                        SagaState.deliverable_id == self.deliverable_id,
                        SagaState.saga_type == SagaType.DELIVERABLE_PRODUCTION
                    )
                )
                saga_state = saga_state_result.scalar_one_or_none()
                
                if saga_state and saga_state.current_state == "REVISIONS_IN_PROGRESS":
                    self.log("✅ SAGA state correctly updated to REVISIONS_IN_PROGRESS")
                else:
                    self.log("❌ SAGA state not updated correctly!")
                    return False

                return True

        except Exception as e:
            self.log(f"❌ Error in reject feedback test: {str(e)}")
            return False

    async def cleanup(self):
        """Clean up test data"""
        self.log("\nCleaning up test data...")
        try:
            async with AsyncSessionLocal() as session:
                # Delete test data in reverse order of creation
                await session.execute(delete(InternalTask).where(InternalTask.deliverable_id == self.deliverable_id))
                await session.execute(delete(ClientFeedback).where(ClientFeedback.deliverable_id == self.deliverable_id))
                await session.execute(delete(ReviewItem).where(ReviewItem.id == self.review_item_id))
                await session.execute(delete(Deliverable).where(Deliverable.id == self.deliverable_id))
                await session.execute(delete(Project).where(Project.id == self.project_id))
                await session.execute(delete(SagaState).where(SagaState.deliverable_id == self.deliverable_id))
                await session.commit()
                self.log("✅ Test data cleanup complete")
        except Exception as e:
            self.log(f"❌ Error during cleanup: {str(e)}")
        finally:
            await close_event_bus()

async def main():
    test = TestFeedbackFlows()
    try:
        await test.setup()
        
        # Test comment feedback
        comment_result = await test.test_comment_feedback()
        print(f"\nComment Feedback Test Result: {'✅ PASSED' if comment_result else '❌ FAILED'}")
        
        # Test reject feedback
        reject_result = await test.test_reject_feedback()
        print(f"\nReject Feedback Test Result: {'✅ PASSED' if reject_result else '❌ FAILED'}")
        
    finally:
        await test.cleanup()

if __name__ == "__main__":
    asyncio.run(main()) 