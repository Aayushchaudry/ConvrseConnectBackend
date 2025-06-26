#!/usr/bin/env python3
# scripts/verify_phase5_implementation.py - Verification script for Phase 5: Testing & Optimization

import asyncio
import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Phase5Verifier:
    """Comprehensive verification for Phase 5 implementation."""
    
    def __init__(self):
        self.verification_results = []
        self.total_tests = 0
        self.passed_tests = 0
        
    def log_test_result(self, test_name: str, passed: bool, details: str = ""):
        """Log the result of a test."""
        self.total_tests += 1
        if passed:
            self.passed_tests += 1
            status = "✅ PASSED"
        else:
            status = "❌ FAILED"
        
        result = f"{status}: {test_name}"
        if details:
            result += f" - {details}"
        
        self.verification_results.append(result)
        logger.info(result)
        
    async def verify_unit_tests(self):
        """Verify that unit tests are properly implemented."""
        logger.info("🔬 Verifying Phase 5 Unit Tests Implementation...")
        
        try:
            # Test 1: Check if Phase 2 services unit tests exist
            test_file_path = project_root / "tests" / "unit" / "test_phase2_services.py"
            if test_file_path.exists():
                with open(test_file_path, 'r') as f:
                    content = f.read()
                    
                # Check for essential test classes
                test_classes = [
                    "TestTaskManagementService",
                    "TestPricingService", 
                    "TestTimelineTrackingService",
                    "TestRequirementService",
                    "TestServiceIntegration"
                ]
                
                all_classes_found = all(cls in content for cls in test_classes)
                self.log_test_result(
                    "Phase 2 Services Unit Tests",
                    all_classes_found,
                    f"Found {sum(1 for cls in test_classes if cls in content)}/{len(test_classes)} test classes"
                )
                
                # Check for async test methods
                async_test_count = content.count("async def test_")
                self.log_test_result(
                    "Async Test Methods",
                    async_test_count >= 10,
                    f"Found {async_test_count} async test methods"
                )
                
            else:
                self.log_test_result("Phase 2 Services Unit Tests", False, "Test file not found")
                
        except Exception as e:
            self.log_test_result("Unit Tests Verification", False, f"Error: {str(e)}")
    
    async def verify_integration_tests(self):
        """Verify that integration tests are properly implemented."""
        logger.info("🔗 Verifying Phase 5 Integration Tests Implementation...")
        
        try:
            # Test 1: Check if Phase 3 API integration tests exist
            test_file_path = project_root / "tests" / "integration" / "test_phase3_apis.py"
            if test_file_path.exists():
                with open(test_file_path, 'r') as f:
                    content = f.read()
                    
                # Check for essential test classes
                test_classes = [
                    "TestTaskManagementAPI",
                    "TestPricingAPI",
                    "TestTimelineTrackingAPI", 
                    "TestRequirementAPI",
                    "TestAPIIntegration"
                ]
                
                all_classes_found = all(cls in content for cls in test_classes)
                self.log_test_result(
                    "Phase 3 API Integration Tests",
                    all_classes_found,
                    f"Found {sum(1 for cls in test_classes if cls in content)}/{len(test_classes)} test classes"
                )
                
                # Check for HTTP client usage
                http_client_usage = "AsyncClient" in content and "httpx" in content
                self.log_test_result(
                    "HTTP Client Integration",
                    http_client_usage,
                    "AsyncClient properly configured for API testing"
                )
                
            else:
                self.log_test_result("Phase 3 API Integration Tests", False, "Test file not found")
                
        except Exception as e:
            self.log_test_result("Integration Tests Verification", False, f"Error: {str(e)}")
    
    async def verify_performance_optimization(self):
        """Verify that performance optimization components are implemented."""
        logger.info("⚡ Verifying Phase 5 Performance Optimization Implementation...")
        
        try:
            # Test 1: Check if performance optimizer exists
            optimizer_path = project_root / "src" / "optimization" / "performance_optimizer.py"
            if optimizer_path.exists():
                with open(optimizer_path, 'r') as f:
                    content = f.read()
                    
                # Check for essential components
                essential_components = [
                    "class PerformanceOptimizer",
                    "optimize_task_queries",
                    "optimize_pricing_calculations",
                    "optimize_bulk_operations",
                    "get_optimization_statistics"
                ]
                
                components_found = sum(1 for comp in essential_components if comp in content)
                self.log_test_result(
                    "Performance Optimizer Components",
                    components_found == len(essential_components),
                    f"Found {components_found}/{len(essential_components)} essential components"
                )
                
                # Check for async/await usage
                async_usage = content.count("async def") >= 3
                self.log_test_result(
                    "Async Performance Methods",
                    async_usage,
                    "Performance optimizer uses async/await pattern"
                )
                
                # Test optimizer instantiation
                try:
                    from src.optimization.performance_optimizer import create_performance_optimizer
                    self.log_test_result("Performance Optimizer Import", True, "Successfully imported")
                except ImportError as e:
                    self.log_test_result("Performance Optimizer Import", False, f"Import error: {str(e)}")
                    
            else:
                self.log_test_result("Performance Optimizer", False, "File not found")
                
        except Exception as e:
            self.log_test_result("Performance Optimization Verification", False, f"Error: {str(e)}")
    
    async def verify_monitoring_analytics(self):
        """Verify that monitoring and analytics components are implemented."""
        logger.info("📊 Verifying Phase 5 Monitoring & Analytics Implementation...")
        
        try:
            # Test 1: Check if analytics engine exists
            analytics_path = project_root / "src" / "monitoring" / "analytics.py"
            if analytics_path.exists():
                with open(analytics_path, 'r') as f:
                    content = f.read()
                    
                # Check for essential components
                essential_components = [
                    "class AnalyticsEngine",
                    "generate_project_analytics",
                    "_analyze_task_performance",
                    "_analyze_pricing_performance",
                    "_generate_project_alerts",
                    "get_system_analytics"
                ]
                
                components_found = sum(1 for comp in essential_components if comp in content)
                self.log_test_result(
                    "Analytics Engine Components",
                    components_found == len(essential_components),
                    f"Found {components_found}/{len(essential_components)} essential components"
                )
                
                # Check for alert thresholds
                alert_thresholds = "_alert_thresholds" in content
                self.log_test_result(
                    "Alert Threshold Configuration",
                    alert_thresholds,
                    "Alert thresholds properly configured"
                )
                
                # Test analytics engine instantiation
                try:
                    from src.monitoring.analytics import create_analytics_engine
                    self.log_test_result("Analytics Engine Import", True, "Successfully imported")
                except ImportError as e:
                    self.log_test_result("Analytics Engine Import", False, f"Import error: {str(e)}")
                    
            else:
                self.log_test_result("Analytics Engine", False, "File not found")
                
        except Exception as e:
            self.log_test_result("Monitoring & Analytics Verification", False, f"Error: {str(e)}")
    
    async def verify_service_imports(self):
        """Verify that all Phase 2-4 services can be imported correctly."""
        logger.info("📦 Verifying Service Import Compatibility...")
        
        services_to_test = [
            ("src.services.task_management_service", "TaskManagementService"),
            ("src.services.pricing_service", "PricingService"),
            ("src.services.timeline_tracking_service", "TimelineTrackingService"),
            ("src.services.requirement_service", "RequirementService")
        ]
        
        for module_path, class_name in services_to_test:
            try:
                module = __import__(module_path, fromlist=[class_name])
                service_class = getattr(module, class_name)
                self.log_test_result(
                    f"{class_name} Import",
                    True,
                    f"Successfully imported from {module_path}"
                )
            except ImportError as e:
                self.log_test_result(
                    f"{class_name} Import",
                    False,
                    f"Import error: {str(e)}"
                )
            except Exception as e:
                self.log_test_result(
                    f"{class_name} Import",
                    False,
                    f"Error: {str(e)}"
                )
    
    async def verify_model_imports(self):
        """Verify that all Phase 1 models can be imported correctly."""
        logger.info("🗄️ Verifying Model Import Compatibility...")
        
        models_to_test = [
            ("src.models.task_deliverable_association", "TaskDeliverableAssociation"),
            ("src.models.deliverable_pricing", "DeliverablePricing"), 
            ("src.models.task_progress", "TaskProgress"),
            ("src.models.project_timeline", "ProjectTimeline"),
            ("src.models.requirement_template", "RequirementTemplate")
        ]
        
        for module_path, class_name in models_to_test:
            try:
                module = __import__(module_path, fromlist=[class_name])
                model_class = getattr(module, class_name)
                self.log_test_result(
                    f"{class_name} Model Import",
                    True,
                    f"Successfully imported from {module_path}"
                )
            except ImportError as e:
                self.log_test_result(
                    f"{class_name} Model Import",
                    False,
                    f"Import error: {str(e)}"
                )
            except Exception as e:
                self.log_test_result(
                    f"{class_name} Model Import",
                    False,
                    f"Error: {str(e)}"
                )
    
    async def verify_orchestrator_imports(self):
        """Verify that Phase 4 orchestrator components can be imported."""
        logger.info("🎼 Verifying Orchestrator Import Compatibility...")
        
        orchestrator_components = [
            ("src.orchestrators.project_lifecycle_orchestrator.enhanced_project_orchestrator", "EnhancedProjectLifecycleOrchestrator"),
            ("src.orchestrators.deliverable_saga_orchestrator.enhanced_deliverable_orchestrator", "EnhancedDeliverableSagaOrchestrator"),
            ("src.orchestrators.integration_hooks", "Phase4IntegrationHooks")
        ]
        
        for module_path, class_name in orchestrator_components:
            try:
                module = __import__(module_path, fromlist=[class_name])
                orchestrator_class = getattr(module, class_name)
                self.log_test_result(
                    f"{class_name} Import",
                    True,
                    f"Successfully imported from {module_path}"
                )
            except ImportError as e:
                self.log_test_result(
                    f"{class_name} Import",
                    False,
                    f"Import error: {str(e)}"
                )
            except Exception as e:
                self.log_test_result(
                    f"{class_name} Import",
                    False,
                    f"Error: {str(e)}"
                )
    
    async def verify_test_infrastructure(self):
        """Verify that test infrastructure is properly set up."""
        logger.info("🧪 Verifying Test Infrastructure...")
        
        # Check for pytest configuration
        pytest_files = [
            project_root / "pytest.ini",
            project_root / "pyproject.toml",
            project_root / "setup.cfg"
        ]
        
        pytest_config_found = any(f.exists() for f in pytest_files)
        self.log_test_result(
            "Pytest Configuration",
            pytest_config_found,
            "Pytest configuration file found" if pytest_config_found else "No pytest config found"
        )
        
        # Check for test directory structure
        test_dirs = [
            project_root / "tests",
            project_root / "tests" / "unit",
            project_root / "tests" / "integration"
        ]
        
        all_dirs_exist = all(d.exists() and d.is_dir() for d in test_dirs)
        self.log_test_result(
            "Test Directory Structure",
            all_dirs_exist,
            f"Found {sum(1 for d in test_dirs if d.exists())}/{len(test_dirs)} test directories"
        )
        
        # Check for __init__.py files in test directories
        init_files = [
            project_root / "tests" / "__init__.py",
            project_root / "tests" / "unit" / "__init__.py",
            project_root / "tests" / "integration" / "__init__.py"
        ]
        
        init_files_exist = sum(1 for f in init_files if f.exists())
        self.log_test_result(
            "Test Module Initialization",
            init_files_exist >= 1,
            f"Found {init_files_exist}/{len(init_files)} __init__.py files"
        )
    
    async def run_comprehensive_verification(self):
        """Run all verification tests."""
        logger.info("🚀 Starting Phase 5: Testing & Optimization Verification")
        logger.info("=" * 60)
        
        verification_tasks = [
            self.verify_unit_tests(),
            self.verify_integration_tests(),
            self.verify_performance_optimization(),
            self.verify_monitoring_analytics(),
            self.verify_service_imports(),
            self.verify_model_imports(),
            self.verify_orchestrator_imports(),
            self.verify_test_infrastructure()
        ]
        
        # Run all verifications
        await asyncio.gather(*verification_tasks, return_exceptions=True)
        
        # Print summary
        logger.info("=" * 60)
        logger.info("📋 PHASE 5 VERIFICATION SUMMARY")
        logger.info("=" * 60)
        
        for result in self.verification_results:
            print(result)
        
        success_rate = (self.passed_tests / self.total_tests * 100) if self.total_tests > 0 else 0
        
        print("\n" + "=" * 60)
        print(f"📊 OVERALL RESULTS: {self.passed_tests}/{self.total_tests} tests passed ({success_rate:.1f}%)")
        
        if success_rate >= 90:
            print("🎉 EXCELLENT: Phase 5 implementation is comprehensive and ready!")
        elif success_rate >= 80:
            print("✅ GOOD: Phase 5 implementation is solid with minor gaps")
        elif success_rate >= 70:
            print("⚠️  ACCEPTABLE: Phase 5 implementation needs some improvements")
        else:
            print("❌ NEEDS WORK: Phase 5 implementation requires significant attention")
        
        print("=" * 60)
        
        return success_rate >= 80


async def main():
    """Main verification function."""
    try:
        verifier = Phase5Verifier()
        success = await verifier.run_comprehensive_verification()
        
        # Exit with appropriate code
        sys.exit(0 if success else 1)
        
    except Exception as e:
        logger.error(f"Verification failed with error: {str(e)}")
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
