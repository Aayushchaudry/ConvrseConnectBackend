# src/services/task_management_service.py

import logging
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload

from src.models.internal_task import InternalTask, TaskStatus
from src.models.deliverable import Deliverable
from src.models.project import Project
from src.models.task_deliverable_association import TaskDeliverableAssociation

logger = logging.getLogger(__name__)


class TaskManagementService:
    """
    Service layer for enhanced task management with project-level task support,
    task-deliverable associations, and intelligent task sharing.
    """

    def __init__(self, db_session: AsyncSession):
        """
        Initialize the TaskManagementService.
        
        Args:
            db_session: An asynchronous SQLAlchemy database session.
        """
        self.db_session = db_session
        logger.info("TaskManagementService initialized")

    async def create_project_level_task(
        self,
        project_id: UUID,
        title: str,
        description: Optional[str] = None,
        estimated_hours: Optional[Decimal] = None,
        priority: Optional[str] = "MEDIUM",
        created_by: Optional[UUID] = None,
        task_template_id: Optional[UUID] = None,
        deliverable_ids: Optional[List[UUID]] = None,
    ) -> InternalTask:
        """
        Create a new project-level task that can be shared across multiple deliverables.
        
        Args:
            project_id: The project this task belongs to
            title: Task title
            description: Task description
            estimated_hours: Estimated hours for completion
            priority: Task priority (HIGH, MEDIUM, LOW)
            created_by: User who created the task
            task_template_id: Template used to create this task (if any)
            deliverable_ids: List of deliverable IDs to associate with this task
            
        Returns:
            InternalTask: The newly created project-level task
        """
        logger.info(f"Creating project-level task '{title}' for project {project_id}")

        # Validate project exists
        project = await self._get_project_by_id(project_id)
        if not project:
            raise ValueError(f"Project with ID {project_id} not found")

        # Create the project-level task
        new_task = InternalTask(
            project_id=project_id,
            deliverable_id=None,  # Project-level tasks don't have a specific deliverable
            title=title,
            description=description,
            status=TaskStatus.NOT_STARTED,
            priority=priority,
            estimated_hours=estimated_hours,
            actual_hours=Decimal('0.00'),
            is_project_level=True,
            task_template_id=task_template_id,
            created_by=created_by,
        )

        self.db_session.add(new_task)
        await self.db_session.commit()
        await self.db_session.refresh(new_task)

        logger.info(f"Created project-level task with ID: {new_task.id}")

        # Associate with deliverables if specified
        if deliverable_ids:
            for deliverable_id in deliverable_ids:
                await self.associate_task_with_deliverable(
                    task_id=new_task.id,
                    deliverable_id=deliverable_id,
                    is_primary_deliverable=(deliverable_id == deliverable_ids[0]),
                    estimated_hours=estimated_hours
                )

        return new_task

    async def associate_task_with_deliverable(
        self,
        task_id: UUID,
        deliverable_id: UUID,
        is_primary_deliverable: bool = False,
        estimated_hours: Optional[Decimal] = None,
        actual_hours: Optional[Decimal] = None,
    ) -> TaskDeliverableAssociation:
        """
        Associate an existing task with a deliverable.
        
        Args:
            task_id: ID of the task to associate
            deliverable_id: ID of the deliverable
            is_primary_deliverable: Whether this is the primary deliverable for the task
            estimated_hours: Estimated hours for this specific association
            actual_hours: Actual hours spent (defaults to 0)
            
        Returns:
            TaskDeliverableAssociation: The created association
        """
        logger.info(f"Associating task {task_id} with deliverable {deliverable_id}")

        # Validate task and deliverable exist and belong to same project
        task = await self._get_task_by_id(task_id)
        if not task:
            raise ValueError(f"Task with ID {task_id} not found")

        deliverable = await self._get_deliverable_by_id(deliverable_id)
        if not deliverable:
            raise ValueError(f"Deliverable with ID {deliverable_id} not found")

        if task.project_id != deliverable.project_id:
            raise ValueError("Task and deliverable must belong to the same project")

        # Check if association already exists
        existing_association = await self._get_task_deliverable_association(task_id, deliverable_id)
        if existing_association:
            logger.warning(f"Association between task {task_id} and deliverable {deliverable_id} already exists")
            return existing_association

        # Create new association
        association = TaskDeliverableAssociation(
            task_id=task_id,
            deliverable_id=deliverable_id,
            is_primary_deliverable=is_primary_deliverable,
            estimated_hours=estimated_hours or task.estimated_hours,
            actual_hours=actual_hours or Decimal('0.00'),
        )

        self.db_session.add(association)
        await self.db_session.commit()
        await self.db_session.refresh(association)

        logger.info(f"Created task-deliverable association with ID: {association.id}")
        return association

    async def remove_task_deliverable_association(
        self,
        task_id: UUID,
        deliverable_id: UUID,
    ) -> bool:
        """
        Remove association between a task and deliverable.
        
        Args:
            task_id: ID of the task
            deliverable_id: ID of the deliverable
            
        Returns:
            bool: True if association was removed, False if not found
        """
        logger.info(f"Removing association between task {task_id} and deliverable {deliverable_id}")

        association = await self._get_task_deliverable_association(task_id, deliverable_id)
        if not association:
            logger.warning(f"No association found between task {task_id} and deliverable {deliverable_id}")
            return False

        await self.db_session.delete(association)
        await self.db_session.commit()

        logger.info(f"Removed task-deliverable association")
        return True

    async def get_shared_tasks_for_project(self, project_id: UUID) -> List[InternalTask]:
        """
        Get all shared (project-level) tasks for a project.
        
        Args:
            project_id: ID of the project
            
        Returns:
            List[InternalTask]: List of project-level tasks
        """
        logger.info(f"Getting shared tasks for project {project_id}")

        result = await self.db_session.execute(
            select(InternalTask)
            .filter(
                and_(
                    InternalTask.project_id == project_id,
                    InternalTask.is_project_level == True
                )
            )
            .options(selectinload(InternalTask.task_deliverable_associations))
        )
        
        tasks = result.scalars().all()
        logger.info(f"Found {len(tasks)} shared tasks for project {project_id}")
        return tasks

    async def get_deliverables_for_task(self, task_id: UUID) -> List[Deliverable]:
        """
        Get all deliverables associated with a specific task.
        
        Args:
            task_id: ID of the task
            
        Returns:
            List[Deliverable]: List of associated deliverables
        """
        logger.info(f"Getting deliverables for task {task_id}")

        result = await self.db_session.execute(
            select(Deliverable)
            .join(TaskDeliverableAssociation)
            .filter(TaskDeliverableAssociation.task_id == task_id)
        )
        
        deliverables = result.scalars().all()
        logger.info(f"Found {len(deliverables)} deliverables for task {task_id}")
        return deliverables

    async def find_similar_tasks_in_project(
        self,
        project_id: UUID,
        task_title: str,
        similarity_threshold: float = 0.7,
    ) -> List[InternalTask]:
        """
        Find existing tasks in the project that are similar to the given title.
        Uses simple string similarity for now - can be enhanced with ML models.
        
        Args:
            project_id: ID of the project to search in
            task_title: Title to search for similar tasks
            similarity_threshold: Minimum similarity score (0.0 to 1.0)
            
        Returns:
            List[InternalTask]: List of similar tasks
        """
        logger.info(f"Finding similar tasks for '{task_title}' in project {project_id}")

        # Get all tasks in the project
        result = await self.db_session.execute(
            select(InternalTask)
            .filter(InternalTask.project_id == project_id)
        )
        
        all_tasks = result.scalars().all()
        similar_tasks = []

        # Simple similarity check using normalized string comparison
        task_title_lower = task_title.lower().strip()
        
        for task in all_tasks:
            existing_title_lower = task.title.lower().strip()
            
            # Calculate simple similarity score
            similarity = self._calculate_string_similarity(task_title_lower, existing_title_lower)
            
            if similarity >= similarity_threshold:
                similar_tasks.append(task)
                logger.info(f"Found similar task: '{task.title}' (similarity: {similarity:.2f})")

        logger.info(f"Found {len(similar_tasks)} similar tasks")
        return similar_tasks

    async def suggest_task_sharing(
        self,
        project_id: UUID,
        task_title: str,
        deliverable_id: UUID,
    ) -> Dict[str, Any]:
        """
        Suggest whether to share an existing task or create a new one.
        
        Args:
            project_id: ID of the project
            task_title: Title of the task to create
            deliverable_id: ID of the deliverable requesting the task
            
        Returns:
            Dict containing suggestion details
        """
        logger.info(f"Getting task sharing suggestions for '{task_title}' in project {project_id}")

        similar_tasks = await self.find_similar_tasks_in_project(project_id, task_title)
        
        suggestions = {
            "should_share": False,
            "similar_tasks": [],
            "recommendation": "create_new",
            "reasoning": "",
        }

        if similar_tasks:
            # Check if any similar tasks are already project-level
            project_level_tasks = [task for task in similar_tasks if task.is_project_level]
            
            if project_level_tasks:
                suggestions.update({
                    "should_share": True,
                    "similar_tasks": [
                        {
                            "id": str(task.id),
                            "title": task.title,
                            "is_project_level": task.is_project_level,
                            "status": task.status,
                        }
                        for task in project_level_tasks
                    ],
                    "recommendation": "share_existing",
                    "reasoning": f"Found {len(project_level_tasks)} similar project-level task(s) that can be shared",
                })
            else:
                suggestions.update({
                    "should_share": True,
                    "similar_tasks": [
                        {
                            "id": str(task.id),
                            "title": task.title,
                            "is_project_level": task.is_project_level,
                            "status": task.status,
                        }
                        for task in similar_tasks
                    ],
                    "recommendation": "convert_to_shared",
                    "reasoning": f"Found {len(similar_tasks)} similar deliverable-specific task(s) that could be converted to project-level",
                })

        if not similar_tasks:
            suggestions["reasoning"] = "No similar tasks found - safe to create new task"

        logger.info(f"Task sharing suggestion: {suggestions['recommendation']}")
        return suggestions

    async def create_or_share_task(
        self,
        project_id: UUID,
        title: str,
        deliverable_id: UUID,
        description: Optional[str] = None,
        estimated_hours: Optional[Decimal] = None,
        priority: Optional[str] = "MEDIUM",
        created_by: Optional[UUID] = None,
        force_create_new: bool = False,
    ) -> Tuple[InternalTask, bool, str]:
        """
        Smart task creation that considers sharing existing tasks.
        
        Args:
            project_id: ID of the project
            title: Task title
            deliverable_id: ID of the deliverable requesting the task
            description: Task description
            estimated_hours: Estimated hours
            priority: Task priority
            created_by: User creating the task
            force_create_new: Force creation of new task even if similar exists
            
        Returns:
            Tuple[InternalTask, bool, str]: (task, was_shared, action_taken)
        """
        logger.info(f"Smart task creation for '{title}' in project {project_id}")

        if not force_create_new:
            # Get sharing suggestions
            suggestions = await self.suggest_task_sharing(project_id, title, deliverable_id)
            
            if suggestions["should_share"] and suggestions["recommendation"] == "share_existing":
                # Use existing project-level task
                similar_task = suggestions["similar_tasks"][0]
                task_id = UUID(similar_task["id"])
                
                # Associate with deliverable
                await self.associate_task_with_deliverable(
                    task_id=task_id,
                    deliverable_id=deliverable_id,
                    estimated_hours=estimated_hours
                )
                
                task = await self._get_task_by_id(task_id)
                return task, True, "shared_existing_task"

        # Create new task (either forced or no suitable existing task found)
        if force_create_new:
            # Create deliverable-specific task
            new_task = InternalTask(
                project_id=project_id,
                deliverable_id=deliverable_id,
                title=title,
                description=description,
                status=TaskStatus.NOT_STARTED,
                priority=priority,
                estimated_hours=estimated_hours,
                actual_hours=Decimal('0.00'),
                is_project_level=False,
                created_by=created_by,
            )
        else:
            # Create project-level task for potential sharing
            new_task = await self.create_project_level_task(
                project_id=project_id,
                title=title,
                description=description,
                estimated_hours=estimated_hours,
                priority=priority,
                created_by=created_by,
                deliverable_ids=[deliverable_id],
            )
            return new_task, False, "created_project_level_task"

        self.db_session.add(new_task)
        await self.db_session.commit()
        await self.db_session.refresh(new_task)

        return new_task, False, "created_deliverable_specific_task"

    # Helper methods

    async def _get_project_by_id(self, project_id: UUID) -> Optional[Project]:
        """Get project by ID."""
        result = await self.db_session.execute(
            select(Project).filter(Project.id == project_id)
        )
        return result.scalar_one_or_none()

    async def _get_task_by_id(self, task_id: UUID) -> Optional[InternalTask]:
        """Get task by ID."""
        result = await self.db_session.execute(
            select(InternalTask).filter(InternalTask.id == task_id)
        )
        return result.scalar_one_or_none()

    async def _get_deliverable_by_id(self, deliverable_id: UUID) -> Optional[Deliverable]:
        """Get deliverable by ID."""
        result = await self.db_session.execute(
            select(Deliverable).filter(Deliverable.id == deliverable_id)
        )
        return result.scalar_one_or_none()

    async def _get_task_deliverable_association(
        self, task_id: UUID, deliverable_id: UUID
    ) -> Optional[TaskDeliverableAssociation]:
        """Get existing task-deliverable association."""
        result = await self.db_session.execute(
            select(TaskDeliverableAssociation).filter(
                and_(
                    TaskDeliverableAssociation.task_id == task_id,
                    TaskDeliverableAssociation.deliverable_id == deliverable_id,
                )
            )
        )
        return result.scalar_one_or_none()

    def _calculate_string_similarity(self, str1: str, str2: str) -> float:
        """
        Calculate simple string similarity using Jaccard similarity of words.
        Can be enhanced with more sophisticated algorithms.
        """
        if str1 == str2:
            return 1.0
        
        # Split into words and create sets
        words1 = set(str1.split())
        words2 = set(str2.split())
        
        if not words1 or not words2:
            return 0.0
        
        # Calculate Jaccard similarity
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0 