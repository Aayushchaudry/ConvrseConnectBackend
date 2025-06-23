#!/usr/bin/env python3

import asyncio
import uuid
from datetime import datetime
import sys
import os
from sqlalchemy import select

# Add the src directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.config.database import AsyncSessionLocal
from src.config.event_bus import get_event_bus, close_event_bus
from src.models.project import Project
from src.models.deliverable import Deliverable, DeliverableType, DeliverableStatus
from src.models.review_item import ReviewItem, ReviewItemType, ReviewStatus
from src.models.internal_task import InternalTask, TaskStatus, TaskType, Priority
from src.models.client_feedback import ClientFeedback, FeedbackType
from src.models.project_output import ProjectOutput
from src.models.saga_state import SagaState
from src.models.requirement import Requirement

# Import services and orchestrators
from src.services.info_gathering_service import InformationGatheringService
from src.services.delivery_service import DeliveryService
from src.orchestrators.deliverable_saga_orchestrator.deliverable_saga_orchestrator import DeliverableSagaOrchestrator
from src.orchestrators.deliverable_saga_orchestrator.commands import GenerateFinalOutputCommand

# Import events and commands
from src.events.project_events import ProjectCreatedEvent, DeliverableDeliveredEvent
from src.events.deliverable_events import DeliverableInfoGatheredEvent
from src.events.client_feedback_events import ClientFeedbackSubmittedEvent
from src.commands.project_commands import StartInformationGatheringCommand

class DirectSagaFlowTest:
    def __init__(self):
        self.project_id = None
        self.deliverable_id = None
        self.internal_task_id = None
        self.review_item_id = None
        self.event_bus = None
        self.info_gathering_service = None
        self.delivery_service = None
        self.deliverable_orchestrator = None
        
    def log(self, message):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        
    async def setup_services(self):
        """Initialize services for direct testing"""
        self.log("Setting up services...")
        try:
            self.event_bus = await get_event_bus()
            self.info_gathering_service = InformationGatheringService(AsyncSessionLocal, self.event_bus)
            self.delivery_service = DeliveryService(AsyncSessionLocal, self.event_bus)
            self.deliverable_orchestrator = DeliverableSagaOrchestrator(AsyncSessionLocal, self.event_bus)
            self.log("✅ Services initialized successfully")
            return True
        except Exception as e:
            self.log(f"❌ Failed to initialize services: {e}")
            return False
            
    async def cleanup_services(self):
        """Clean up services"""
        if self.event_bus:
            await close_event_bus()
            self.log("✅ Services cleaned up")
            
    async def create_project_and_deliverable(self):
        """Create project and deliverable in database"""
        self.log("Step 1: Creating project and deliverable...")
        
        self.project_id = str(uuid.uuid4())
        self.deliverable_id = str(uuid.uuid4())
        
        try:
            async with AsyncSessionLocal() as session:
                # Create Project
                project = Project(
                    id=self.project_id,
                    name="Direct SAGA Test Project"
                )
                session.add(project)
                
                # Create Deliverable
                deliverable = Deliverable(
                    id=self.deliverable_id,
                    project_id=self.project_id,
                    deliverable_type=DeliverableType.RENDERED_IMAGES,
                    deliverable_sub_type="Interior",
                    current_status=DeliverableStatus.INFO_GATHERING,
                    tentative_timeline_days=40
                )
                session.add(deliverable)
                
                await session.commit()
                self.log(f"✅ Project created: {self.project_id}")
                self.log(f"✅ Deliverable created: {self.deliverable_id}")
                return True
                
        except Exception as e:
            self.log(f"❌ Failed to create project/deliverable: {e}")
            return False
            
    async def test_info_gathering_service_directly(self):
        """Test the InformationGatheringService directly"""
        self.log("Step 2: Testing InformationGatheringService directly...")
        
        try:
            # Create the command
            command = StartInformationGatheringCommand(
                project_id=self.project_id,
                deliverable_ids=[self.deliverable_id]
            )
            
            # Call the service directly
            await self.info_gathering_service.handle_start_information_gathering_command(command)
            self.log("✅ InformationGatheringService executed successfully")
            
            # Check if requirements were created
            async with AsyncSessionLocal() as session:
                requirements_result = await session.execute(
                    select(Requirement).where(
                        Requirement.project_id == self.project_id,
                        Requirement.deliverable_id == self.deliverable_id
                    )
                )
                requirements = requirements_result.scalars().all()
                self.log(f"✅ Found {len(requirements)} requirement(s) created:")
                for req in requirements:
                    self.log(f"   - {req.requirement_name}: {req.status.value}")
                
                return len(requirements) > 0
                
        except Exception as e:
            self.log(f"❌ Failed to test info gathering service: {e}")
            return False
            
    async def create_internal_task_and_review_item(self):
        """Create internal task and review item to simulate production completion"""
        self.log("Step 3: Creating internal task and review item...")
        
        self.internal_task_id = str(uuid.uuid4())
        self.review_item_id = str(uuid.uuid4())
        
        try:
            async with AsyncSessionLocal() as session:
                # Create Internal Task first
                task = InternalTask(
                    id=self.internal_task_id,
                    project_id=self.project_id,
                    deliverable_id=self.deliverable_id,
                    task_name="Modeling Room Complete",
                    task_type=TaskType.MODELING,
                    status=TaskStatus.DONE,
                    priority=Priority.NORMAL
                )
                session.add(task)
                await session.flush()  # Flush to ensure the task exists before creating review item
                
                # Create Review Item
                review_item = ReviewItem(
                    id=self.review_item_id,
                    project_id=self.project_id,
                    deliverable_id=self.deliverable_id,
                    source_internal_task_id=self.internal_task_id,
                    item_type=ReviewItemType.STATIC_RENDER,
                    item_url="http://example.com/final_approved_render.jpg",
                    description="Final draft for client approval",
                    review_status=ReviewStatus.PENDING_REVIEW
                )
                session.add(review_item)
                
                await session.commit()
                self.log(f"✅ Internal Task created: {self.internal_task_id}")
                self.log(f"✅ Review Item created: {self.review_item_id}")
                return True
                
        except Exception as e:
            self.log(f"❌ Failed to create task/review item: {e}")
            return False
            
    async def submit_feedback_and_test_orchestrator(self):
        """Submit ACCEPT feedback and test deliverable orchestrator directly"""
        self.log("Step 4: Creating feedback and testing deliverable orchestrator...")
        
        feedback_id = str(uuid.uuid4())
        
        try:
            async with AsyncSessionLocal() as session:
                # Create Client Feedback
                feedback = ClientFeedback(
                    id=feedback_id,
                    review_item_id=self.review_item_id,
                    project_id=self.project_id,
                    deliverable_id=self.deliverable_id,
                    feedback_type=FeedbackType.ACCEPT,
                    comment_text="Looks perfect! Final approval."
                )
                session.add(feedback)
                
                # Update Review Item status
                review_item = await session.get(ReviewItem, self.review_item_id)
                if review_item:
                    review_item.review_status = ReviewStatus.ACCEPTED
                
                await session.commit()
                self.log(f"✅ ACCEPT feedback submitted: {feedback_id}")
                
                # Test delivery orchestrator directly with feedback event
                feedback_event = ClientFeedbackSubmittedEvent(
                    project_id=self.project_id,
                    deliverable_id=self.deliverable_id,
                    review_item_id=self.review_item_id,
                    client_user_id=None,
                    feedback_type="ACCEPT",
                    comment_text="Looks perfect! Final approval."
                )
                
                # Call deliverable orchestrator directly
                await self.deliverable_orchestrator.on_client_feedback_submitted(feedback_event)
                self.log("✅ DeliverableSagaOrchestrator executed successfully")
                
                return True
                
        except Exception as e:
            self.log(f"❌ Failed to test delivery service: {e}")
            return False
            
    async def test_delivery_service_directly(self):
        """Test the delivery service directly with the command the orchestrator would have published"""
        self.log("Step 5: Testing delivery service with final output command...")
        
        try:
            # Create the command that the orchestrator would have published
            command = GenerateFinalOutputCommand(
                project_id=self.project_id,
                deliverable_id=self.deliverable_id,
                output_name="Final Deliverable Output"
            )
            
            # Call the delivery service directly
            await self.delivery_service.handle_generate_final_output_command(command)
            self.log("✅ DeliveryService executed successfully")
            
            # Verify project output was created
            async with AsyncSessionLocal() as session:
                output_result = await session.execute(
                    select(ProjectOutput).where(
                        ProjectOutput.project_id == self.project_id,
                        ProjectOutput.deliverable_id == self.deliverable_id
                    )
                )
                outputs = output_result.scalars().all()
                self.log(f"✅ Found {len(outputs)} project output(s) created:")
                for output in outputs:
                    self.log(f"   - {output.output_name}: {output.output_url}")
                
                return len(outputs) > 0
                
        except Exception as e:
            self.log(f"❌ Failed to test delivery service: {e}")
            return False
            
    async def verify_final_results(self):
        """Verify the final results of the complete flow"""
        self.log("Step 5: Verifying final results...")
        
        try:
            async with AsyncSessionLocal() as session:
                # Check Requirements
                requirements_result = await session.execute(
                    select(Requirement).where(
                        Requirement.project_id == self.project_id,
                        Requirement.deliverable_id == self.deliverable_id
                    )
                )
                requirements = requirements_result.scalars().all()
                
                # Check Project Outputs
                output_result = await session.execute(
                    select(ProjectOutput).where(
                        ProjectOutput.project_id == self.project_id,
                        ProjectOutput.deliverable_id == self.deliverable_id
                    )
                )
                outputs = output_result.scalars().all()
                
                # Check Client Feedback
                feedback_result = await session.execute(
                    select(ClientFeedback).where(ClientFeedback.review_item_id == self.review_item_id)
                )
                feedbacks = feedback_result.scalars().all()
                
                # Check SAGA States
                saga_result = await session.execute(
                    select(SagaState).where(SagaState.project_id == self.project_id)
                )
                saga_states = saga_result.scalars().all()
                
                self.log("📊 FINAL RESULTS:")
                self.log(f"   Requirements: {len(requirements)}")
                self.log(f"   Project Outputs: {len(outputs)}")
                for output in outputs:
                    self.log(f"      - {output.output_name}: {output.output_url}")
                self.log(f"   Client Feedbacks: {len(feedbacks)}")
                self.log(f"   SAGA States: {len(saga_states)}")
                
                # Success criteria
                success = (len(requirements) > 0 and 
                          len(outputs) > 0 and 
                          len(feedbacks) > 0)
                
                if success:
                    self.log("🎉 DIRECT SAGA FLOW TEST PASSED!")
                else:
                    self.log("❌ SAGA flow incomplete")
                
                return success
                
        except Exception as e:
            self.log(f"❌ Failed final verification: {e}")
            return False
            
    async def run_direct_saga_test(self):
        """Execute the direct SAGA flow test"""
        self.log("🚀 Starting DIRECT SAGA Flow Test")
        self.log("=" * 60)
        
        steps = [
            ("Setup Services", self.setup_services),
            ("Create Project & Deliverable", self.create_project_and_deliverable),
            ("Test Info Gathering Service", self.test_info_gathering_service_directly),
            ("Create Task & Review Item", self.create_internal_task_and_review_item),
            ("Test Orchestrator", self.submit_feedback_and_test_orchestrator),
            ("Test Delivery Service", self.test_delivery_service_directly),
            ("Verify Final Results", self.verify_final_results)
        ]
        
        success = True
        for step_name, step_func in steps:
            self.log(f"\n📋 {step_name}")
            if not await step_func():
                self.log(f"❌ Test failed at step: {step_name}")
                success = False
                break
                
        await self.cleanup_services()
        
        if success:
            self.log("\n" + "=" * 60)
            self.log("🎉 DIRECT SAGA FLOW TEST COMPLETED SUCCESSFULLY!")
            self.log(f"📊 Summary:")
            self.log(f"   Project ID: {self.project_id}")
            self.log(f"   Deliverable ID: {self.deliverable_id}")
            self.log(f"   Internal Task ID: {self.internal_task_id}")
            self.log(f"   Review Item ID: {self.review_item_id}")
        else:
            self.log("❌ DIRECT SAGA FLOW TEST FAILED")
            
        return success

async def main():
    test = DirectSagaFlowTest()
    success = await test.run_direct_saga_test()
    return 0 if success else 1

if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(result) 