#!/usr/bin/env python3
"""
Auth Integration Test Script for ConvrseConnectBackend
Tests the integration with auth-service
"""
import asyncio
import os
import sys
import logging
from typing import Dict, Any

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from integrations.auth_service_client import get_auth_client, AuthServiceError
from config.auth_config import get_auth_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AuthIntegrationTester:
    """Tests auth integration functionality"""
    
    def __init__(self):
        self.results = {
            "tests_run": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "errors": []
        }
    
    def log_result(self, test_name: str, passed: bool, error: str = None):
        """Log test result"""
        self.results["tests_run"] += 1
        if passed:
            self.results["tests_passed"] += 1
            logger.info(f"✅ {test_name} - PASSED")
        else:
            self.results["tests_failed"] += 1
            logger.error(f"❌ {test_name} - FAILED: {error}")
            self.results["errors"].append(f"{test_name}: {error}")
    
    async def test_auth_config(self):
        """Test auth configuration loading"""
        test_name = "Auth Configuration Loading"
        try:
            config = get_auth_config()
            assert config.auth_service_url, "Auth service URL not configured"
            assert config.jwt_secret_key, "JWT secret key not configured"
            assert config.auth_service_token, "Auth service token not configured"
            self.log_result(test_name, True)
        except Exception as e:
            self.log_result(test_name, False, str(e))
    
    async def test_auth_client_initialization(self):
        """Test auth client initialization"""
        test_name = "Auth Client Initialization"
        try:
            auth_client = await get_auth_client()
            assert auth_client is not None, "Auth client is None"
            self.log_result(test_name, True)
        except Exception as e:
            self.log_result(test_name, False, str(e))
    
    async def test_auth_service_health(self):
        """Test auth service health check"""
        test_name = "Auth Service Health Check"
        try:
            auth_client = await get_auth_client()
            health_status = await auth_client.health_check()
            if health_status:
                self.log_result(test_name, True)
            else:
                self.log_result(test_name, False, "Auth service health check returned False")
        except Exception as e:
            self.log_result(test_name, False, str(e))
    
    async def test_token_validation_invalid(self):
        """Test token validation with invalid token"""
        test_name = "Invalid Token Validation"
        try:
            auth_client = await get_auth_client()
            # This should raise an exception for invalid token
            try:
                await auth_client.validate_token("invalid_token")
                self.log_result(test_name, False, "Expected token validation to fail")
            except AuthServiceError:
                # Expected behavior
                self.log_result(test_name, True)
        except Exception as e:
            self.log_result(test_name, False, str(e))
    
    async def test_circuit_breaker(self):
        """Test circuit breaker functionality"""
        test_name = "Circuit Breaker Functionality"
        try:
            auth_client = await get_auth_client()
            circuit_breaker = auth_client.circuit_breaker
            
            # Test that circuit breaker starts in CLOSED state
            assert circuit_breaker.can_attempt_call(), "Circuit breaker should allow calls initially"
            
            # Simulate failures
            for _ in range(circuit_breaker.failure_threshold):
                circuit_breaker.call_failed()
            
            # Circuit breaker should be OPEN now
            assert not circuit_breaker.can_attempt_call(), "Circuit breaker should be OPEN after failures"
            
            # Test recovery
            circuit_breaker.call_succeeded()
            assert circuit_breaker.can_attempt_call(), "Circuit breaker should recover after success"
            
            self.log_result(test_name, True)
        except Exception as e:
            self.log_result(test_name, False, str(e))
    
    async def run_all_tests(self):
        """Run all integration tests"""
        logger.info("🚀 Starting Auth Integration Tests...")
        logger.info("=" * 50)
        
        # Run tests
        await self.test_auth_config()
        await self.test_auth_client_initialization()
        await self.test_auth_service_health()
        await self.test_token_validation_invalid()
        await self.test_circuit_breaker()
        
        # Print summary
        logger.info("=" * 50)
        logger.info("📊 Test Results Summary:")
        logger.info(f"   Tests Run: {self.results['tests_run']}")
        logger.info(f"   Passed: {self.results['tests_passed']}")
        logger.info(f"   Failed: {self.results['tests_failed']}")
        
        if self.results["errors"]:
            logger.info("\n❌ Errors:")
            for error in self.results["errors"]:
                logger.info(f"   - {error}")
        
        success_rate = (self.results["tests_passed"] / self.results["tests_run"]) * 100
        logger.info(f"   Success Rate: {success_rate:.1f}%")
        
        if self.results["tests_failed"] == 0:
            logger.info("🎉 All tests passed!")
        else:
            logger.info(f"⚠️  {self.results['tests_failed']} test(s) failed")
        
        return self.results["tests_failed"] == 0


async def main():
    """Main test runner"""
    # Set up environment variables for testing
    os.environ.setdefault("AUTH_SERVICE_URL", "http://localhost:8001")
    os.environ.setdefault("AUTH_SERVICE_TOKEN", "test_token")
    os.environ.setdefault("JWT_SECRET_KEY", "test_secret_key_minimum_32_chars_long")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    
    tester = AuthIntegrationTester()
    success = await tester.run_all_tests()
    
    # Clean up
    from integrations.auth_service_client import close_auth_client
    await close_auth_client()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main()) 