#!/usr/bin/env python3

import asyncio
import uuid
import requests
import json
from datetime import datetime
import time
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

# Import events and commands
from src.events.project_events import ProjectCreatedEvent, DeliverableDeliveredEvent
from src.events.deliverable_events import DeliverableInfoGatheredEvent
from src.events.client_feedback_events import ClientFeedbackSubmittedEvent
from src.commands.project_commands import StartInformationGatheringCommand

# Configuration
API_BASE_URL = "http://127.0.0.1:8000/api/v1"

class FullSagaDeliveryFlowTest:
    def __init__(self):
        self.project_id = None
        self.deliverable_id = None
        self.internal_task_id = None
        self.review_item_id = None
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
            
    async def create_project_and_deliverable_with_events(self):
        """Create project and deliverable, then publish events to trigger SAGA"""
        self.log("Step 1: Creating project and deliverable with event publishing...")
        
        self.project_id = str(uuid.uuid4())
        self.deliverable_id = str(uuid.uuid4())
        
        try:
            async with AsyncSessionLocal() as session:
                # Create Project
                project = Project(
                    id=self.project_id,
                    name="Full SAGA Test Project"
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
                
                # Publish ProjectCreatedEvent
                project_created_event = ProjectCreatedEvent(
                    project_id=self.project_id,
                    project_name="Full SAGA Test Project",
                    initial_status="initiated"
                )
                
                await self.event_bus.publish(
                    topic="project.created",
                    message=project_created_event
                )
                self.log("✅ ProjectCreatedEvent published")
                
                # Instead of DeliverableCreatedEvent, let's simulate info gathering completed
                # Publish DeliverableInfoGatheredEvent to trigger production
                info_gathered_event = DeliverableInfoGatheredEvent(
                    project_id=self.project_id,
                    deliverable_id=self.deliverable_id
                )
                
                await self.event_bus.publish(
                    topic="deliverable.info_gathered",
                    message=info_gathered_event
                )
                self.log("✅ DeliverableInfoGatheredEvent published")
                
                # Also publish StartInformationGatheringCommand directly
                start_info_command = StartInformationGatheringCommand(
                    project_id=self.project_id,
                    deliverable_ids=[self.deliverable_id]
                )
                
                await self.event_bus.publish(
                    topic="project.command.start_information_gathering",
                    message=start_info_command
                )
                self.log("✅ StartInformationGatheringCommand published")
                
                return True
                
        except Exception as e:
            self.log(f"❌ Failed to create project/deliverable: {e}")
            return False
            
    async def wait_for_info_gathering_processing(self):
        """Wait for information gathering service to process and create requirements"""
        self.log("Step 2: Waiting for information gathering processing...")
        
        # Wait for processing
        await asyncio.sleep(10)
        
        try:
            async with AsyncSessionLocal() as session:
                # Check if requirements were created
                requirements_result = await session.execute(
                    select(Requirement).where(
                        Requirement.project_id == self.project_id,
                        Requirement.deliverable_id == self.deliverable_id
                    )
                )
                requirements = requirements_result.scalars().all()
                self.log(f"✅ Found {len(requirements)} requirement(s) created by info gathering service")
                
                # Check SAGA state
                saga_result = await session.execute(
                    select(SagaState).where(SagaState.project_id == self.project_id)
                )
                saga_states = saga_result.scalars().all()
                self.log(f"✅ Found {len(saga_states)} SAGA state(s):")
                for saga in saga_states:
                    self.log(f"   - Type: {saga.saga_type.value}, State: {saga.current_state}, Status: {saga.status.value}")
                
                return len(requirements) > 0
                
        except Exception as e:
            self.log(f"❌ Failed to check info gathering results: {e}")
            return False
            
    async def create_internal_task_and_review_item(self):
        """Create internal task and review item to simulate production completion"""
        self.log("Step 3: Creating internal task and review item...")
        
        self.internal_task_id = str(uuid.uuid4())
        self.review_item_id = str(uuid.uuid4())
        
        try:
            async with AsyncSessionLocal() as session:
                # Create Internal Task
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
                
                # Create Review Item
                review_item = ReviewItem(
                    id=self.review_item_id,
                    project_id=self.project_id,
                    deliverable_id=self.deliverable_id,
                    source_internal_task_id=self.internal_task_id,
                    item_type=ReviewItemType.STATIC_RENDER,
                    item_url="http://example.com/final_approved_render.jpg",
                    description="Final draft for client approval",
                    review_status=ReviewStatus.PENDING
                )
                session.add(review_item)
                
                await session.commit()
                self.log(f"✅ Internal Task created: {self.internal_task_id}")
                self.log(f"✅ Review Item created: {self.review_item_id}")
                return True
                
        except Exception as e:
            self.log(f"❌ Failed to create task/review item: {e}")
            return False
            
    async def submit_accept_feedback_with_event(self):
        """Submit ACCEPT feedback and publish event to trigger final delivery"""
        self.log("Step 4: Submitting ACCEPT feedback with event publishing...")
        
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
                
                # Publish ClientFeedbackSubmittedEvent
                feedback_event = ClientFeedbackSubmittedEvent(
                    project_id=self.project_id,
                    deliverable_id=self.deliverable_id,
                    review_item_id=self.review_item_id,
                    client_user_id=None,
                    feedback_type="ACCEPT",
                    comment_text="Looks perfect! Final approval."
                )
                
                await self.event_bus.publish(
                    topic="client.feedback.submitted",
                    message=feedback_event
                )
                self.log("✅ ClientFeedbackSubmittedEvent published")
                
                return True
                
        except Exception as e:
            self.log(f"❌ Failed to submit feedback: {e}")
            return False
            
    async def wait_for_delivery_processing(self):
        """Wait for delivery service to process and create project outputs"""
        self.log("Step 5: Waiting for delivery processing...")
        
        # Wait for processing
        await asyncio.sleep(15)
        
        try:
            async with AsyncSessionLocal() as session:
                # Check if project outputs were created
                output_result = await session.execute(
                    select(ProjectOutput).where(
                        ProjectOutput.project_id == self.project_id,
                        ProjectOutput.deliverable_id == self.deliverable_id
                    )
                )
                output_records = output_result.scalars().all()
                self.log(f"🎯 Found {len(output_records)} ProjectOutput record(s):")
                for record in output_records:
                    self.log(f"   - Output ID: {record.id}")
                    self.log(f"   - Name: {record.output_name}")
                    self.log(f"   - URL: {record.output_url}")
                
                # Check final SAGA state
                saga_result = await session.execute(
                    select(SagaState).where(SagaState.project_id == self.project_id)
                )
                saga_states = saga_result.scalars().all()
                self.log(f"✅ Final SAGA state(s):")
                for saga in saga_states:
                    self.log(f"   - Type: {saga.saga_type.value}, State: {saga.current_state}, Status: {saga.status.value}")
                
                return len(output_records) > 0
                
        except Exception as e:
            self.log(f"❌ Failed to check delivery results: {e}")
            return False
            
    async def verify_complete_flow(self):
        """Final verification of the complete SAGA flow"""
        self.log("Step 6: Final verification...")
        
        try:
            async with AsyncSessionLocal() as session:
                # Comprehensive verification
                
                # Check Requirements
                requirements_result = await session.execute(
                    select(Requirement).where(
                        Requirement.project_id == self.project_id,
                        Requirement.deliverable_id == self.deliverable_id
                    )
                )
                requirements = requirements_result.scalars().all()
                
                # Check SAGA States
                saga_result = await session.execute(
                    select(SagaState).where(SagaState.project_id == self.project_id)
                )
                saga_states = saga_result.scalars().all()
                
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
                
                self.log("📊 FINAL VERIFICATION RESULTS:")
                self.log(f"   Requirements: {len(requirements)}")
                self.log(f"   SAGA States: {len(saga_states)}")
                self.log(f"   Project Outputs: {len(outputs)}")
                self.log(f"   Client Feedbacks: {len(feedbacks)}")
                
                # Success criteria: We should have requirements and at least one deliverable SAGA completed
                success = (len(requirements) > 0 and 
                          len(saga_states) > 0 and 
                          len(feedbacks) > 0)
                
                if success:
                    self.log("🎉 COMPLETE SAGA FLOW VERIFICATION PASSED!")
                else:
                    self.log("❌ SAGA flow incomplete - some components missing")
                
                return success
                
        except Exception as e:
            self.log(f"❌ Failed final verification: {e}")
            return False
            
    async def run_full_saga_test(self):
        """Execute the complete SAGA flow test"""
        self.log("🚀 Starting COMPLETE SAGA Delivery Flow Test")
        self.log("=" * 70)
        
        steps = [
            ("Setup Event Bus", self.setup_event_bus),
            ("Create Project & Deliverable + Events", self.create_project_and_deliverable_with_events),
            ("Wait for Info Gathering Processing", self.wait_for_info_gathering_processing),
            ("Create Internal Task & Review Item", self.create_internal_task_and_review_item),
            ("Submit ACCEPT Feedback + Event", self.submit_accept_feedback_with_event),
            ("Wait for Delivery Processing", self.wait_for_delivery_processing),
            ("Verify Complete Flow", self.verify_complete_flow)
        ]
        
        success = True
        for step_name, step_func in steps:
            self.log(f"\n📋 {step_name}")
            if not await step_func():
                self.log(f"❌ Test failed at step: {step_name}")
                success = False
                break
                
        await self.cleanup_event_bus()
        
        if success:
            self.log("\n" + "=" * 70)
            self.log("🎉 COMPLETE SAGA DELIVERY FLOW TEST PASSED!")
            self.log(f"📊 Test Summary:")
            self.log(f"   Project ID: {self.project_id}")
            self.log(f"   Deliverable ID: {self.deliverable_id}")
            self.log(f"   Internal Task ID: {self.internal_task_id}")
            self.log(f"   Review Item ID: {self.review_item_id}")
        else:
            self.log("❌ COMPLETE SAGA FLOW TEST FAILED")
            
        return success

async def main():
    test = FullSagaDeliveryFlowTest()
    success = await test.run_full_saga_test()
    return 0 if success else 1

if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(result) 