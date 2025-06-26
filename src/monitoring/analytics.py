# src/monitoring/analytics.py - Monitoring and analytics for Phase 2-4 components

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, func

logger = logging.getLogger(__name__)


class AnalyticsEngine:
    """
    Analytics engine for ConvrseConnect Backend Enhancement components.
    Provides insights and monitoring for Phases 2-4 functionality.
    """

    def __init__(self, db_session: AsyncSession):
        """Initialize the analytics engine."""
        self.db_session = db_session
        self._metrics_cache = {}
        self._alert_thresholds = {
            "task_completion_rate": 70.0,
            "budget_variance_threshold": 20.0,
            "timeline_delay_threshold": 5  # days
        }

    async def generate_project_analytics(self, project_id: UUID, days_back: int = 30) -> Dict[str, Any]:
        """
        Generate comprehensive analytics for a project.
        
        Args:
            project_id: The project ID to analyze
            days_back: Number of days to look back for analysis
            
        Returns:
            Dictionary containing project analytics
        """
        try:
            logger.info(f"Generating analytics for project {project_id}")
            
            # Get project overview data
            project_overview = await self._get_project_overview(project_id)
            
            # Get task completion analytics
            task_analytics = await self._analyze_task_performance(project_id, days_back)
            
            # Get pricing analytics
            pricing_analytics = await self._analyze_pricing_performance(project_id)
            
            # Generate alerts and recommendations
            alerts = await self._generate_project_alerts(project_id, task_analytics, pricing_analytics)
            
            analytics_result = {
                "project_id": str(project_id),
                "generated_at": datetime.now().isoformat(),
                "analysis_period_days": days_back,
                "overview": project_overview,
                "task_analytics": task_analytics,
                "pricing_analytics": pricing_analytics,
                "alerts": alerts,
                "summary": {
                    "health_score": self._calculate_project_health_score(task_analytics, pricing_analytics),
                    "risk_level": self._assess_project_risk(alerts),
                    "recommendations": self._generate_recommendations(task_analytics, pricing_analytics)
                }
            }
            
            logger.info(f"Analytics generation completed for project {project_id}")
            return analytics_result
            
        except Exception as e:
            logger.error(f"Error generating project analytics: {str(e)}")
            raise

    async def _get_project_overview(self, project_id: UUID) -> Dict[str, Any]:
        """Get basic project overview metrics."""
        try:
            overview_query = text("""
                SELECT 
                    p.title as project_title,
                    p.status as project_status,
                    p.start_date,
                    p.end_date,
                    COUNT(DISTINCT t.id) as total_tasks,
                    COUNT(DISTINCT CASE WHEN t.status = 'completed' THEN t.id END) as completed_tasks
                FROM projects p
                LEFT JOIN internal_tasks t ON p.id = t.project_id
                WHERE p.id = :project_id
                GROUP BY p.id, p.title, p.status, p.start_date, p.end_date
            """)
            
            result = await self.db_session.execute(overview_query, {"project_id": str(project_id)})
            row = result.fetchone()
            
            if row:
                completion_rate = (row.completed_tasks / row.total_tasks * 100) if row.total_tasks > 0 else 0
                
                return {
                    "project_title": row.project_title,
                    "project_status": row.project_status,
                    "start_date": row.start_date.isoformat() if row.start_date else None,
                    "end_date": row.end_date.isoformat() if row.end_date else None,
                    "total_tasks": row.total_tasks,
                    "completed_tasks": row.completed_tasks,
                    "completion_rate": round(completion_rate, 2)
                }
            
            return {}
            
        except Exception as e:
            logger.error(f"Error getting project overview: {str(e)}")
            raise

    async def _analyze_task_performance(self, project_id: UUID, days_back: int) -> Dict[str, Any]:
        """Analyze task performance metrics."""
        try:
            task_performance_query = text("""
                SELECT 
                    t.status,
                    t.priority,
                    t.estimated_hours,
                    COUNT(*) as task_count
                FROM internal_tasks t
                WHERE t.project_id = :project_id
                GROUP BY t.status, t.priority, t.estimated_hours
                ORDER BY t.priority DESC
            """)
            
            result = await self.db_session.execute(task_performance_query, {"project_id": str(project_id)})
            rows = result.fetchall()
            
            # Analyze task performance
            tasks_by_status = defaultdict(int)
            tasks_by_priority = defaultdict(int)
            total_estimated_hours = 0
            
            for row in rows:
                tasks_by_status[row.status] += row.task_count
                tasks_by_priority[row.priority] += row.task_count
                total_estimated_hours += (row.estimated_hours or 0) * row.task_count
            
            total_tasks = sum(tasks_by_status.values())
            completion_rate = (tasks_by_status.get("completed", 0) / total_tasks * 100) if total_tasks > 0 else 0
            
            return {
                "total_tasks": total_tasks,
                "tasks_by_status": dict(tasks_by_status),
                "tasks_by_priority": dict(tasks_by_priority),
                "total_estimated_hours": total_estimated_hours,
                "productivity_metrics": {
                    "tasks_completed_rate": round(completion_rate, 2),
                    "high_priority_completion": round(tasks_by_priority.get("high", 0) / total_tasks * 100, 2) if total_tasks > 0 else 0,
                    "efficiency_score": 85  # Simplified efficiency metric
                }
            }
            
        except Exception as e:
            logger.error(f"Error analyzing task performance: {str(e)}")
            raise

    async def _analyze_pricing_performance(self, project_id: UUID) -> Dict[str, Any]:
        """Analyze pricing performance metrics."""
        try:
            pricing_query = text("""
                SELECT 
                    dp.base_price,
                    dp.markup_percentage,
                    dp.discount_percentage,
                    dp.final_price
                FROM deliverable_pricing dp
                WHERE dp.project_id = :project_id
                ORDER BY dp.final_price DESC
            """)
            
            result = await self.db_session.execute(pricing_query, {"project_id": str(project_id)})
            rows = result.fetchall()
            
            if not rows:
                return {
                    "total_budget": 0,
                    "average_markup": 0,
                    "average_discount": 0,
                    "budget_efficiency": 0
                }
            
            # Calculate pricing metrics
            total_base_cost = sum(row.base_price for row in rows)
            total_final_price = sum(row.final_price for row in rows)
            average_markup = sum(row.markup_percentage for row in rows) / len(rows)
            average_discount = sum(row.discount_percentage for row in rows) / len(rows)
            
            return {
                "total_budget": float(total_final_price),
                "total_base_cost": float(total_base_cost),
                "average_markup": round(average_markup, 2),
                "average_discount": round(average_discount, 2),
                "budget_efficiency": round((total_final_price / total_base_cost - 1) * 100, 2) if total_base_cost > 0 else 0,
                "profit_margin": round(((total_final_price - total_base_cost) / total_final_price) * 100, 2) if total_final_price > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Error analyzing pricing performance: {str(e)}")
            raise

    async def _generate_project_alerts(self, project_id: UUID, task_analytics: Dict, pricing_analytics: Dict) -> List[Dict[str, Any]]:
        """Generate alerts based on analytics data."""
        alerts = []
        
        try:
            # Task completion rate alert
            completion_rate = task_analytics.get("productivity_metrics", {}).get("tasks_completed_rate", 0)
            if completion_rate < self._alert_thresholds["task_completion_rate"]:
                alerts.append({
                    "type": "task_completion",
                    "severity": "warning" if completion_rate > 50 else "critical",
                    "message": f"Task completion rate ({completion_rate}%) is below threshold ({self._alert_thresholds['task_completion_rate']}%)",
                    "suggested_action": "Review task assignments and remove blockers"
                })
            
            # Pricing coverage alert
            if pricing_analytics.get("total_budget", 0) == 0:
                alerts.append({
                    "type": "pricing_coverage",
                    "severity": "warning",
                    "message": "No pricing information available for project deliverables",
                    "suggested_action": "Set up pricing for all deliverables to enable budget tracking"
                })
            
            logger.info(f"Generated {len(alerts)} alerts for project {project_id}")
            return alerts
            
        except Exception as e:
            logger.error(f"Error generating project alerts: {str(e)}")
            return []

    def _calculate_project_health_score(self, task_analytics: Dict, pricing_analytics: Dict) -> int:
        """Calculate overall project health score (0-100)."""
        try:
            # Task completion score (60% weight)
            task_score = task_analytics.get("productivity_metrics", {}).get("tasks_completed_rate", 0) * 0.6
            
            # Budget efficiency score (40% weight)
            efficiency = task_analytics.get("productivity_metrics", {}).get("efficiency_score", 0)
            budget_score = efficiency * 0.4
            
            total_score = int(task_score + budget_score)
            return max(0, min(100, total_score))
            
        except Exception as e:
            logger.error(f"Error calculating health score: {str(e)}")
            return 50  # Default neutral score

    def _assess_project_risk(self, alerts: List[Dict]) -> str:
        """Assess overall project risk level."""
        try:
            if not alerts:
                return "low"
            
            critical_alerts = sum(1 for alert in alerts if alert.get("severity") == "critical")
            warning_alerts = sum(1 for alert in alerts if alert.get("severity") == "warning")
            
            if critical_alerts >= 2:
                return "high"
            elif critical_alerts >= 1 or warning_alerts >= 3:
                return "medium"
            else:
                return "low"
                
        except Exception as e:
            logger.error(f"Error assessing project risk: {str(e)}")
            return "unknown"

    def _generate_recommendations(self, task_analytics: Dict, pricing_analytics: Dict) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []
        
        try:
            # Task-based recommendations
            completion_rate = task_analytics.get("productivity_metrics", {}).get("tasks_completed_rate", 0)
            if completion_rate < 70:
                recommendations.append("Focus on completing high-priority tasks to improve project momentum")
            
            # Pricing recommendations
            if pricing_analytics.get("total_budget", 0) == 0:
                recommendations.append("Establish pricing for all deliverables to enable comprehensive budget tracking")
            
            if not recommendations:
                recommendations.append("Project is performing well - maintain current practices")
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error generating recommendations: {str(e)}")
            return ["Unable to generate recommendations due to data analysis error"]

    async def get_system_analytics(self) -> Dict[str, Any]:
        """Get system-wide analytics across all projects."""
        try:
            system_query = text("""
                SELECT 
                    COUNT(DISTINCT p.id) as total_projects,
                    COUNT(DISTINCT t.id) as total_tasks,
                    COUNT(DISTINCT CASE WHEN t.status = 'completed' THEN t.id END) as completed_tasks,
                    COUNT(DISTINCT CASE WHEN p.status = 'completed' THEN p.id END) as completed_projects
                FROM projects p
                LEFT JOIN internal_tasks t ON p.id = t.project_id
            """)
            
            result = await self.db_session.execute(system_query)
            row = result.fetchone()
            
            if row:
                return {
                    "total_projects": row.total_projects or 0,
                    "completed_projects": row.completed_projects or 0,
                    "project_completion_rate": round((row.completed_projects / row.total_projects * 100), 2) if row.total_projects > 0 else 0,
                    "total_tasks": row.total_tasks or 0,
                    "completed_tasks": row.completed_tasks or 0,
                    "task_completion_rate": round((row.completed_tasks / row.total_tasks * 100), 2) if row.total_tasks > 0 else 0,
                    "generated_at": datetime.now().isoformat()
                }
            
            return {}
            
        except Exception as e:
            logger.error(f"Error getting system analytics: {str(e)}")
            raise


# Factory function for creating analytics engine instances
def create_analytics_engine(db_session: AsyncSession) -> AnalyticsEngine:
    """
    Factory function to create an AnalyticsEngine instance.
    
    Args:
        db_session: Database session
        
    Returns:
        AnalyticsEngine instance
    """
    return AnalyticsEngine(db_session=db_session)
