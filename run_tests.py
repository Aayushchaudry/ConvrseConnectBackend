#!/usr/bin/env python3
"""
Comprehensive Test Runner for ConvrseConnectBackend
Runs unit tests, integration tests, security tests, and e2e tests with coverage reporting.
"""

import os
import sys
import subprocess
import argparse
import time
from pathlib import Path
from typing import List, Dict, Optional
import json


class TestRunner:
    """Comprehensive test runner for the ConvrseConnectBackend project."""
    
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.test_results = {}
        self.total_start_time = time.time()
        
    def run_command(self, command: List[str], description: str) -> Dict:
        """Run a command and capture results."""
        print(f"\n{'='*60}")
        print(f"Running: {description}")
        print(f"Command: {' '.join(command)}")
        print(f"{'='*60}")
        
        start_time = time.time()
        
        try:
            result = subprocess.run(
                command,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            duration = time.time() - start_time
            
            print(f"Exit code: {result.returncode}")
            print(f"Duration: {duration:.2f} seconds")
            
            if result.stdout:
                print(f"\nSTDOUT:\n{result.stdout}")
            
            if result.stderr:
                print(f"\nSTDERR:\n{result.stderr}")
            
            return {
                'success': result.returncode == 0,
                'exit_code': result.returncode,
                'duration': duration,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'description': description
            }
            
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            print(f"Command timed out after {duration:.2f} seconds")
            return {
                'success': False,
                'exit_code': -1,
                'duration': duration,
                'stdout': '',
                'stderr': 'Command timed out',
                'description': description
            }
        except Exception as e:
            duration = time.time() - start_time
            print(f"Error running command: {e}")
            return {
                'success': False,
                'exit_code': -1,
                'duration': duration,
                'stdout': '',
                'stderr': str(e),
                'description': description
            }
    
    def check_dependencies(self) -> bool:
        """Check if required dependencies are installed."""
        print("Checking dependencies...")
        
        required_packages = [
            'pytest',
            'pytest-asyncio',
            'pytest-cov',
            'httpx',
            'fastapi',
            'sqlalchemy',
            'asyncpg'
        ]
        
        missing_packages = []
        
        for package in required_packages:
            try:
                __import__(package.replace('-', '_'))
                print(f"✓ {package}")
            except ImportError:
                missing_packages.append(package)
                print(f"✗ {package}")
        
        if missing_packages:
            print(f"\nMissing packages: {', '.join(missing_packages)}")
            print("Install them with: pip install " + " ".join(missing_packages))
            return False
        
        print("All dependencies are installed.")
        return True
    
    def setup_test_environment(self) -> bool:
        """Set up test environment variables."""
        print("Setting up test environment...")
        
        test_env = {
            'ENV': 'test',
            'DEBUG': 'true',
            'DATABASE_URL': 'postgresql+asyncpg://test_user:test_pass@localhost:5433/test_project_db',
            'KAFKA_BOOTSTRAP_SERVERS': 'localhost:9092',
            'ACTIVE_EVENT_BUS': 'kafka',
            'PYTHONPATH': str(self.project_root)
        }
        
        for key, value in test_env.items():
            os.environ[key] = value
            print(f"Set {key}={value}")
        
        return True
    
    def run_unit_tests(self, coverage: bool = True) -> Dict:
        """Run unit tests."""
        command = ['python', '-m', 'pytest', 'tests/unit/', '-v']
        
        if coverage:
            command.extend([
                '--cov=src',
                '--cov-report=term-missing',
                '--cov-report=html:htmlcov/unit',
                '--cov-report=xml:coverage-unit.xml'
            ])
        
        command.extend([
            '--tb=short',
            '-m', 'unit',
            '--durations=10'
        ])
        
        result = self.run_command(command, "Unit Tests")
        self.test_results['unit_tests'] = result
        return result
    
    def run_integration_tests(self, coverage: bool = True) -> Dict:
        """Run integration tests."""
        command = ['python', '-m', 'pytest', 'tests/integration/', '-v']
        
        if coverage:
            command.extend([
                '--cov=src',
                '--cov-append',
                '--cov-report=term-missing',
                '--cov-report=html:htmlcov/integration',
                '--cov-report=xml:coverage-integration.xml'
            ])
        
        command.extend([
            '--tb=short',
            '-m', 'integration',
            '--durations=10'
        ])
        
        result = self.run_command(command, "Integration Tests")
        self.test_results['integration_tests'] = result
        return result
    
    def run_security_tests(self) -> Dict:
        """Run security tests."""
        command = [
            'python', '-m', 'pytest', 
            'tests/security/', 
            '-v',
            '--tb=short',
            '-m', 'security',
            '--durations=10'
        ]
        
        result = self.run_command(command, "Security Tests")
        self.test_results['security_tests'] = result
        return result
    
    def run_e2e_tests(self) -> Dict:
        """Run end-to-end tests."""
        command = [
            'python', '-m', 'pytest', 
            'tests/e2e/', 
            '-v',
            '--tb=short',
            '-m', 'e2e',
            '--durations=10'
        ]
        
        result = self.run_command(command, "End-to-End Tests")
        self.test_results['e2e_tests'] = result
        return result
    
    def run_performance_tests(self) -> Dict:
        """Run performance tests."""
        command = [
            'python', '-m', 'pytest', 
            'tests/', 
            '-v',
            '--tb=short',
            '-m', 'slow',
            '--durations=10'
        ]
        
        result = self.run_command(command, "Performance Tests")
        self.test_results['performance_tests'] = result
        return result
    
    def run_linting(self) -> Dict:
        """Run code linting."""
        commands = [
            (['python', '-m', 'flake8', 'src/', 'tests/'], "Flake8 Linting"),
            (['python', '-m', 'black', '--check', 'src/', 'tests/'], "Black Code Formatting Check"),
            (['python', '-m', 'mypy', 'src/'], "MyPy Type Checking")
        ]
        
        results = {}
        for command, description in commands:
            result = self.run_command(command, description)
            results[description.lower().replace(' ', '_')] = result
        
        self.test_results['linting'] = results
        return results
    
    def run_security_scan(self) -> Dict:
        """Run security vulnerability scan."""
        commands = [
            (['python', '-m', 'safety', 'check'], "Safety Security Scan"),
            (['python', '-m', 'bandit', '-r', 'src/'], "Bandit Security Scan")
        ]
        
        results = {}
        for command, description in commands:
            result = self.run_command(command, description)
            results[description.lower().replace(' ', '_')] = result
        
        self.test_results['security_scan'] = results
        return results
    
    def generate_coverage_report(self) -> Dict:
        """Generate combined coverage report."""
        command = [
            'python', '-m', 'coverage', 'combine',
            '&&',
            'python', '-m', 'coverage', 'report',
            '&&',
            'python', '-m', 'coverage', 'html', '-d', 'htmlcov/combined'
        ]
        
        result = self.run_command(command, "Combined Coverage Report")
        self.test_results['coverage_report'] = result
        return result
    
    def run_all_tests(self, 
                     include_unit: bool = True,
                     include_integration: bool = True,
                     include_security: bool = True,
                     include_e2e: bool = True,
                     include_performance: bool = False,
                     include_linting: bool = True,
                     include_security_scan: bool = True,
                     coverage: bool = True) -> Dict:
        """Run all specified test suites."""
        
        print(f"\n{'='*80}")
        print("COMPREHENSIVE TEST SUITE EXECUTION")
        print(f"{'='*80}")
        
        # Check dependencies
        if not self.check_dependencies():
            return {'success': False, 'error': 'Missing dependencies'}
        
        # Setup environment
        if not self.setup_test_environment():
            return {'success': False, 'error': 'Failed to setup test environment'}
        
        # Run linting first
        if include_linting:
            self.run_linting()
        
        # Run security scan
        if include_security_scan:
            self.run_security_scan()
        
        # Run test suites
        if include_unit:
            self.run_unit_tests(coverage=coverage)
        
        if include_integration:
            self.run_integration_tests(coverage=coverage)
        
        if include_security:
            self.run_security_tests()
        
        if include_e2e:
            self.run_e2e_tests()
        
        if include_performance:
            self.run_performance_tests()
        
        # Generate coverage report
        if coverage and (include_unit or include_integration):
            self.generate_coverage_report()
        
        return self.test_results
    
    def print_summary(self):
        """Print test execution summary."""
        total_duration = time.time() - self.total_start_time
        
        print(f"\n{'='*80}")
        print("TEST EXECUTION SUMMARY")
        print(f"{'='*80}")
        print(f"Total execution time: {total_duration:.2f} seconds")
        
        # Count results
        total_tests = 0
        passed_tests = 0
        failed_tests = 0
        
        for test_type, result in self.test_results.items():
            if isinstance(result, dict) and 'success' in result:
                total_tests += 1
                if result['success']:
                    passed_tests += 1
                    status = "✓ PASSED"
                else:
                    failed_tests += 1
                    status = "✗ FAILED"
                
                duration = result.get('duration', 0)
                print(f"{test_type:30} {status:10} ({duration:.2f}s)")
            
            elif isinstance(result, dict):
                # Handle nested results (like linting)
                for sub_test, sub_result in result.items():
                    if isinstance(sub_result, dict) and 'success' in sub_result:
                        total_tests += 1
                        if sub_result['success']:
                            passed_tests += 1
                            status = "✓ PASSED"
                        else:
                            failed_tests += 1
                            status = "✗ FAILED"
                        
                        duration = sub_result.get('duration', 0)
                        print(f"{sub_test:30} {status:10} ({duration:.2f}s)")
        
        print(f"\n{'='*80}")
        print(f"TOTAL: {total_tests} tests")
        print(f"PASSED: {passed_tests} tests")
        print(f"FAILED: {failed_tests} tests")
        print(f"SUCCESS RATE: {(passed_tests/total_tests*100):.1f}%" if total_tests > 0 else "N/A")
        print(f"{'='*80}")
        
        # Save results to JSON
        results_file = self.project_root / 'test_results.json'
        with open(results_file, 'w') as f:
            json.dump(self.test_results, f, indent=2, default=str)
        print(f"Detailed results saved to: {results_file}")
        
        return failed_tests == 0


def main():
    """Main entry point for the test runner."""
    parser = argparse.ArgumentParser(description='Comprehensive Test Runner for ConvrseConnectBackend')
    
    parser.add_argument('--unit', action='store_true', default=True,
                       help='Run unit tests (default: True)')
    parser.add_argument('--no-unit', action='store_true',
                       help='Skip unit tests')
    parser.add_argument('--integration', action='store_true', default=True,
                       help='Run integration tests (default: True)')
    parser.add_argument('--no-integration', action='store_true',
                       help='Skip integration tests')
    parser.add_argument('--security', action='store_true', default=True,
                       help='Run security tests (default: True)')
    parser.add_argument('--no-security', action='store_true',
                       help='Skip security tests')
    parser.add_argument('--e2e', action='store_true', default=True,
                       help='Run end-to-end tests (default: True)')
    parser.add_argument('--no-e2e', action='store_true',
                       help='Skip end-to-end tests')
    parser.add_argument('--performance', action='store_true',
                       help='Run performance tests (default: False)')
    parser.add_argument('--linting', action='store_true', default=True,
                       help='Run linting checks (default: True)')
    parser.add_argument('--no-linting', action='store_true',
                       help='Skip linting checks')
    parser.add_argument('--security-scan', action='store_true', default=True,
                       help='Run security vulnerability scan (default: True)')
    parser.add_argument('--no-security-scan', action='store_true',
                       help='Skip security vulnerability scan')
    parser.add_argument('--no-coverage', action='store_true',
                       help='Skip coverage reporting')
    parser.add_argument('--quick', action='store_true',
                       help='Run only unit and integration tests')
    parser.add_argument('--full', action='store_true',
                       help='Run all tests including performance tests')
    
    args = parser.parse_args()
    
    # Handle quick mode
    if args.quick:
        args.no_security = True
        args.no_e2e = True
        args.no_linting = True
        args.no_security_scan = True
    
    # Handle full mode
    if args.full:
        args.performance = True
    
    # Determine what to run
    include_unit = not args.no_unit
    include_integration = not args.no_integration
    include_security = not args.no_security
    include_e2e = not args.no_e2e
    include_performance = args.performance
    include_linting = not args.no_linting
    include_security_scan = not args.no_security_scan
    coverage = not args.no_coverage
    
    # Create and run test runner
    runner = TestRunner()
    
    try:
        results = runner.run_all_tests(
            include_unit=include_unit,
            include_integration=include_integration,
            include_security=include_security,
            include_e2e=include_e2e,
            include_performance=include_performance,
            include_linting=include_linting,
            include_security_scan=include_security_scan,
            coverage=coverage
        )
        
        success = runner.print_summary()
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n\nTest execution interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main() 