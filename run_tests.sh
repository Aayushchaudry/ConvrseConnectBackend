#!/bin/bash

# =============================================================================
# CONVRSE CONNECT BACKEND - COMPREHENSIVE TEST RUNNER
# =============================================================================
# This script sets up the testing environment and runs all test categories:
# - Unit Tests
# - Integration Tests  
# - Security Tests
# - End-to-End Tests
# - Performance Tests
# - Coverage Reports
# - Code Quality Analysis
# =============================================================================

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="convrse-connect-backend"
PYTHON_VERSION="3.13"
VENV_NAME="venv"
TEST_DB_NAME="test_convrse_connect.db"
COVERAGE_THRESHOLD=48
LOG_FILE="test_results.log"

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

print_banner() {
    echo -e "${CYAN}"
    echo "============================================================================="
    echo "  $1"
    echo "============================================================================="
    echo -e "${NC}"
}

print_section() {
    echo -e "${BLUE}▶ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${PURPLE}ℹ️  $1${NC}"
}

# =============================================================================
# ENVIRONMENT SETUP
# =============================================================================

setup_environment() {
    print_banner "SETTING UP TEST ENVIRONMENT"
    
    # Check if Python is available
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is not installed. Please install Python 3.13 or higher."
        exit 1
    fi
    
    PYTHON_CMD=$(command -v python3)
    PYTHON_ACTUAL_VERSION=$($PYTHON_CMD --version 2>&1 | cut -d' ' -f2)
    print_info "Using Python: $PYTHON_CMD (version $PYTHON_ACTUAL_VERSION)"
    
    # Check virtual environment
    if [[ -z "$VIRTUAL_ENV" ]]; then
        if [[ -d "$VENV_NAME" ]]; then
            print_section "Activating existing virtual environment: $VENV_NAME"
            source $VENV_NAME/bin/activate
            print_success "Virtual environment activated"
        else
            print_section "Creating virtual environment: $VENV_NAME"
            $PYTHON_CMD -m venv $VENV_NAME
            source $VENV_NAME/bin/activate
            print_success "Virtual environment created and activated"
        fi
    else
        print_success "Virtual environment already active: $VIRTUAL_ENV"
    fi
    
    # Upgrade pip
    print_section "Upgrading pip"
    python -m pip install --upgrade pip --quiet
    print_success "Pip upgraded"
    
    # Install dependencies
    print_section "Installing dependencies"
    if [ -f "requirements.txt" ]; then
        print_info "Installing from requirements.txt..."
        pip install -r requirements.txt --quiet
        print_success "Dependencies installed successfully"
    else
        print_error "requirements.txt not found!"
        exit 1
    fi
    
    # Install testing dependencies
    print_section "Installing testing dependencies"
    TESTING_PACKAGES=(
        "pytest>=8.4.0"
        "pytest-asyncio>=1.0.0"
        "pytest-mock>=3.12.0"
        "pytest-cov>=6.1.1"
        "httpx>=0.28.1"
        "pytest-xdist>=3.3.1"
        "pytest-html>=4.1.0"
        "pytest-json-report>=1.5.0"
        "pytest-timeout>=2.1.0"
        "asyncpg>=0.30.0"
        "aiosqlite>=0.21.0"
        "sqlalchemy-utils>=0.41.2"
    )
    
    for package in "${TESTING_PACKAGES[@]}"; do
        pip install "$package" --quiet 2>/dev/null || print_warning "Failed to install $package"
    done
    
    print_success "Testing dependencies installed"
    
    # Install code quality dependencies
    QUALITY_PACKAGES=(
        "black>=25.1.0"
        "flake8>=7.2.0"
        "flake8-docstrings>=1.7.0"
        "flake8-import-order>=0.18.2"
        "flake8-black>=0.3.6"
        "flake8-isort>=6.1.1"
        "mypy>=1.16.0"
        "pylint>=3.0.0"
        "bandit[toml]>=1.8.3"
        "safety>=3.5.2"
        "isort>=6.0.1"
    )
    
    for package in "${QUALITY_PACKAGES[@]}"; do
        pip install "$package" --quiet 2>/dev/null || print_warning "Failed to install $package"
    done
    
    print_success "Development dependencies installed"
}

# =============================================================================
# DATABASE SETUP
# =============================================================================

setup_test_database() {
    print_banner "SETTING UP TEST DATABASE"
    
    # Remove existing test databases
    rm -f test*.db 2>/dev/null || true
    print_info "Removed existing test databases"
    
    # Set test environment variables
    export ENVIRONMENT="test"
    export TESTING="true"
    export JWT_SECRET_KEY="test-secret-key-for-testing-only-at-least-32-chars"
    export REDIS_URL="redis://localhost:6379/0"
    export KAFKA_BOOTSTRAP_SERVERS="localhost:9092"
    export AUTH_SERVICE_URL="http://localhost:8001"
    export AUTH_SERVICE_TOKEN="test-auth-service-token"
    export ACTIVE_EVENT_BUS="kafka"
    export DEBUG="true"
    export AUTH_CIRCUIT_BREAKER_FAILURE_THRESHOLD="100"
    export AUTH_CIRCUIT_BREAKER_RECOVERY_TIMEOUT="1"
    export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
    
    # Check PostgreSQL availability
    print_section "Checking PostgreSQL availability"
    if command -v psql &> /dev/null; then
        if PGPASSWORD=test_pass psql -h localhost -p 5433 -U test_user -d postgres -c "SELECT 1;" &> /dev/null 2>&1; then
            export DATABASE_URL="postgresql+asyncpg://test_user:test_pass@localhost:5433/test_convrse_db"
            print_success "PostgreSQL is available - using PostgreSQL for tests"
        else
            export DATABASE_URL="sqlite+aiosqlite:///./test_convrse.db"
            print_warning "PostgreSQL not available - falling back to SQLite"
        fi
    else
        export DATABASE_URL="sqlite+aiosqlite:///./test_convrse.db"
        print_info "PostgreSQL client not found - using SQLite"
    fi
    
    print_success "Test database environment configured"
    print_info "Database URL: $DATABASE_URL"
}

# =============================================================================
# CODE QUALITY CHECKS
# =============================================================================

run_code_quality_checks() {
    print_banner "RUNNING CODE QUALITY CHECKS"
    
    # Check if src directory exists
    if [ ! -d "src" ]; then
        print_warning "src directory not found, skipping code quality checks"
        return 0
    fi
    
    # Create reports directory
    mkdir -p reports/quality
    
    local quality_exit_code=0
    
    # Import sorting check with isort
    print_section "Checking import sorting with isort"
    if isort --check-only --diff src tests > reports/quality/isort_report.txt 2>&1; then
        print_success "Import sorting is correct"
    else
        print_warning "Import sorting issues found (run: isort src tests)"
        print_info "Check reports/quality/isort_report.txt for details"
        # Auto-fix import sorting
        print_section "Auto-fixing import sorting"
        isort src tests > reports/quality/isort_fix.txt 2>&1 || true
        print_info "Import sorting issues auto-fixed"
    fi
    
    # Black formatting check
    print_section "Checking code formatting with Black"
    if black --check --diff src tests > reports/quality/black_report.txt 2>&1; then
        print_success "Code formatting is correct"
    else
        print_warning "Code formatting issues found (run: black src tests)"
        # Auto-fix formatting
        print_section "Auto-fixing formatting issues"
        black src tests > reports/quality/black_fix.txt 2>&1 || true
        print_info "Formatting issues auto-fixed"
    fi
    
    # Enhanced Flake8 linting
    print_section "Running comprehensive Flake8 linting"
    if flake8 src tests \
        --output-file=reports/quality/flake8_report.txt \
        --format='%(path)s:%(row)d:%(col)d: %(code)s %(text)s' \
        --statistics \
        --count \
        --exclude=migrations,__pycache__,venv,.venv,.git 2>/dev/null; then
        print_success "No critical linting issues found"
    else
        print_warning "Linting issues found (check reports/quality/flake8_report.txt)"
    fi
    
    # Pylint comprehensive analysis
    print_section "Running Pylint analysis"
    if pylint src --output-format=text \
        --reports=yes \
        --score=yes \
        --disable=C0114,C0115,C0116,R0903,R0913 > reports/quality/pylint_report.txt 2>&1; then
        PYLINT_SCORE=$(tail -n 2 reports/quality/pylint_report.txt | grep "Your code has been rated" | awk '{print $7}' | cut -d'/' -f1 2>/dev/null || echo "0")
        print_success "Pylint analysis completed (Score: ${PYLINT_SCORE:-0}/10)"
    else
        print_warning "Pylint found issues (check reports/quality/pylint_report.txt)"
    fi
    
    # Type checking with MyPy
    print_section "Running type checking with MyPy"
    if mypy src \
        --html-report reports/quality/mypy_html \
        --txt-report reports/quality \
        --cobertura-xml-report reports/quality \
        --junit-xml reports/quality/mypy_junit.xml \
        --ignore-missing-imports \
        --no-strict-optional \
        --allow-untyped-defs 2>/dev/null; then
        print_success "Type checking passed"
    else
        print_warning "Type checking issues found (check reports/quality/mypy.txt)"
    fi
    
    # Security analysis with Bandit
    print_section "Running security analysis with Bandit"
    if bandit -r src \
        -f json -o reports/quality/bandit_report.json \
        -f txt -o reports/quality/bandit_report.txt \
        -f html -o reports/quality/bandit_report.html \
        --severity-level medium \
        --skip B101,B601,B608 2>/dev/null; then
        print_success "Security analysis completed - no issues found"
    else
        print_warning "Security issues found (check reports/quality/bandit_report.html)"
    fi
    
    # Dependency vulnerability scanning
    print_section "Scanning for vulnerable dependencies"
    if safety check \
        --json --output reports/quality/safety_report.json \
        --continue-on-error 2>/dev/null && \
       safety check \
        --output reports/quality/safety_report.txt \
        --continue-on-error 2>/dev/null; then
        print_success "No critical vulnerable dependencies found"
    else
        print_warning "Vulnerable dependencies found (check reports/quality/safety_report.txt)"
    fi
    
    # Generate quality summary report
    print_section "Generating code quality summary"
    cat > reports/quality/quality_summary.txt << EOF
CODE QUALITY ANALYSIS SUMMARY
==============================

Analysis Date: $(date)
Project: $PROJECT_NAME

Checks Performed:
✓ Import Sorting (isort)
✓ Code Formatting (black)  
✓ Linting (flake8)
✓ Code Analysis (pylint)
✓ Type Checking (mypy)
✓ Security Analysis (bandit)
✓ Dependency Scanning (safety)

Reports Generated:
- Import Issues: reports/quality/isort_report.txt
- Formatting Issues: reports/quality/black_report.txt
- Linting Issues: reports/quality/flake8_report.txt
- Code Analysis: reports/quality/pylint_report.txt
- Type Issues: reports/quality/mypy.txt
- Type Report (HTML): reports/quality/mypy_html/index.html
- Security Issues: reports/quality/bandit_report.html
- Vulnerability Report: reports/quality/safety_report.txt

Overall Status: $([ $quality_exit_code -eq 0 ] && echo "PASSED" || echo "ISSUES FOUND")
EOF

    print_success "Code quality analysis completed"
    return 0  # Don't fail build on quality issues
}

# =============================================================================
# TEST EXECUTION
# =============================================================================

run_unit_tests() {
    print_banner "RUNNING UNIT TESTS"
    
    print_section "Executing unit tests"
    echo "Command: pytest tests/unit/ -v --tb=short --durations=10 -x"
    
    if pytest tests/unit/ \
        -v \
        --tb=short \
        --durations=10 \
        -x \
        2>&1 | tee -a $LOG_FILE; then
        print_success "Unit tests passed"
        return 0
    else
        print_error "Unit tests failed"
        return 1
    fi
}

run_integration_tests() {
    print_banner "RUNNING INTEGRATION TESTS"
    
    print_section "Executing integration tests"
    echo "Command: pytest tests/integration/ -v --tb=short --durations=10 -m integration"
    
    if pytest tests/integration/ \
        -v \
        --tb=short \
        --durations=10 \
        -m "integration" \
        2>&1 | tee -a $LOG_FILE; then
        print_success "Integration tests passed"
        return 0
    else
        print_warning "Integration tests failed (not critical)"
        return 0  # Don't fail build for integration tests
    fi
}

run_security_tests() {
    print_banner "RUNNING SECURITY TESTS"
    
    print_section "Executing security tests"
    echo "Command: pytest tests/security/ -v --tb=short --durations=10 -m security"
    
    if pytest tests/security/ \
        -v \
        --tb=short \
        --durations=10 \
        -m "security" \
        2>&1 | tee -a $LOG_FILE; then
        print_success "Security tests passed"
        return 0
    else
        print_error "Security tests failed"
        return 1
    fi
}

run_e2e_tests() {
    print_banner "RUNNING END-TO-END TESTS"
    
    print_section "Executing end-to-end tests"
    print_info "Note: E2E tests will automatically fall back to SQLite if PostgreSQL is unavailable"
    echo "Command: pytest tests/e2e/ -v --tb=short --durations=20 -m e2e"
    
    if pytest tests/e2e/ \
        -v \
        --tb=short \
        --durations=20 \
        -m "e2e" \
        2>&1 | tee -a $LOG_FILE; then
        print_success "End-to-end tests passed"
        return 0
    else
        print_error "End-to-end tests failed - THIS IS BUILD CRITICAL"
        return 1
    fi
}

run_performance_tests() {
    print_banner "RUNNING PERFORMANCE TESTS"
    
    print_section "Executing performance tests"
    echo "Command: pytest -m performance -v --tb=short"
    
    if pytest -m performance -v --tb=short 2>&1 | tee -a $LOG_FILE; then
        print_success "Performance tests passed"
        return 0
    else
        print_warning "Performance tests failed or no performance tests found"
        return 0  # Don't fail the entire suite for performance tests
    fi
}

run_comprehensive_tests() {
    print_banner "RUNNING COMPREHENSIVE TEST SUITE"
    
    local total_exit_code=0
    
    # Run tests by category
    print_section "Running Unit Tests"
    if ! run_unit_tests; then
        total_exit_code=1
    fi
    
    print_section "Running Integration Tests"
    run_integration_tests  # Don't fail on integration tests
    
    print_section "Running Security Tests"
    if ! run_security_tests; then
        total_exit_code=1
    fi
    
    print_section "Running End-to-End Tests"
    if ! run_e2e_tests; then
        total_exit_code=1
    fi
    
    print_section "Running Performance Tests"
    run_performance_tests  # Don't fail on performance tests
    
    return $total_exit_code
}

run_all_tests_with_coverage() {
    print_banner "RUNNING COMPLETE TEST SUITE WITH COVERAGE"
    
    print_section "Executing all tests with coverage analysis"
    
    # Create reports directory
    mkdir -p reports
    
    # Remove old coverage data
    rm -f .coverage .coverage.*
    rm -rf htmlcov/ reports/coverage_html/
    
    # Run tests with coverage and proper configuration
    echo "Command: pytest --cov=src --cov-report=html:reports/coverage_html --cov-report=term-missing --cov-report=json:reports/coverage.json --cov-report=xml:reports/coverage.xml --cov-fail-under=$COVERAGE_THRESHOLD --html=reports/test_report.html --self-contained-html --json-report --json-report-file=reports/test_results.json"
    
    if pytest \
        --cov=src \
        --cov-report=html:reports/coverage_html \
        --cov-report=term-missing:skip-covered \
        --cov-report=json:reports/coverage.json \
        --cov-report=xml:reports/coverage.xml \
        --cov-fail-under=$COVERAGE_THRESHOLD \
        --html=reports/test_report.html \
        --self-contained-html \
        --json-report --json-report-file=reports/test_results.json \
        --tb=short \
        --durations=10 \
        --strict-markers \
        --strict-config \
        -v \
        --asyncio-mode=auto \
        --disable-warnings \
        -m "not integration and not security and not e2e" \
        --ignore=test_scripts/ \
        2>&1 | tee -a $LOG_FILE; then
        print_success "All tests passed with sufficient coverage"
        
        # Run critical tests separately
        print_section "Running critical test suites"
        pytest tests/security/ -v --tb=short -m "security" || true
        pytest tests/e2e/ -v --tb=short -m "e2e" || return 1
        
        return 0
    else
        print_error "Tests failed or coverage below threshold ($COVERAGE_THRESHOLD%)"
        return 1
    fi
}

run_tests_parallel() {
    print_banner "RUNNING TESTS IN PARALLEL"
    
    print_section "Executing tests with parallel workers"
    echo "Command: pytest -n auto --dist=worksteal --tb=short"
    
    if pytest -n auto --dist=worksteal --tb=short 2>&1 | tee -a $LOG_FILE; then
        print_success "Parallel tests completed successfully"
        return 0
    else
        print_error "Parallel tests failed"
        return 1
    fi
}

# =============================================================================
# REPORTING
# =============================================================================

generate_reports() {
    print_banner "GENERATING TEST REPORTS"
    
    # Create reports directory
    mkdir -p reports
    
    print_section "Generating coverage report"
    if [ -f ".coverage" ] || [ -f "reports/coverage.json" ]; then
        # Generate additional coverage reports if not already generated
        if [ -f ".coverage" ] && [ ! -f "reports/coverage_html/index.html" ]; then
            coverage html -d reports/coverage_html 2>/dev/null || true
            coverage json -o reports/coverage.json 2>/dev/null || true
            coverage xml -o reports/coverage.xml 2>/dev/null || true
        fi
        
        # Extract coverage percentage
        COVERAGE_PERCENT="Unknown"
        if [ -f "reports/coverage.json" ]; then
            COVERAGE_PERCENT=$(python -c "
import json
try:
    with open('reports/coverage.json', 'r') as f:
        data = json.load(f)
    print(f\"{data['totals']['percent_covered']:.2f}\")
except Exception as e:
    print('0.00')
" 2>/dev/null || echo "0.00")
        fi
        
        print_success "Coverage report generated: $COVERAGE_PERCENT%"
        print_info "HTML report: reports/coverage_html/index.html"
    else
        COVERAGE_PERCENT="0.00"
        print_warning "No coverage data found"
    fi
    
    # Count actual tests from pytest collection
    print_section "Analyzing test metrics"
    
    # Get comprehensive test counts
    UNIT_TESTS=$(pytest --collect-only tests/unit/ --quiet 2>/dev/null | grep "::test_" | wc -l | tr -d ' ' || echo "0")
    INTEGRATION_TESTS=$(pytest --collect-only tests/integration/ --quiet 2>/dev/null | grep "::test_" | wc -l | tr -d ' ' || echo "0")
    SECURITY_TESTS=$(pytest --collect-only tests/security/ --quiet 2>/dev/null | grep "::test_" | wc -l | tr -d ' ' || echo "0")
    E2E_TESTS=$(pytest --collect-only tests/e2e/ --quiet 2>/dev/null | grep "::test_" | wc -l | tr -d ' ' || echo "0")
    TOTAL_TESTS=$(pytest --collect-only --quiet 2>/dev/null | grep "::test_" | wc -l | tr -d ' ' || echo "0")
    
    # Parse test results if available
    TEST_RESULTS_STATUS="Not Available"
    PASSED_TESTS="0"
    FAILED_TESTS="0"
    SKIPPED_TESTS="0"
    
    if [ -f "reports/test_results.json" ]; then
        TEST_RESULTS_STATUS=$(python -c "
import json
try:
    with open('reports/test_results.json', 'r') as f:
        data = json.load(f)
    summary = data.get('summary', {})
    print(f\"Passed: {summary.get('passed', 0)}, Failed: {summary.get('failed', 0)}, Skipped: {summary.get('skipped', 0)}\")
except:
    print('Error parsing results')
" 2>/dev/null || echo "Error parsing results")
    fi
    
    # Generate comprehensive test summary
    print_section "Generating comprehensive test summary"
    cat > reports/test_summary.txt << EOF
CONVRSE CONNECT BACKEND COMPREHENSIVE TEST REPORT
=================================================

Execution Details:
-----------------
Date: $(date)
Python Version: $(python --version 2>/dev/null || echo "Unknown")
Project Directory: $(pwd)
Environment: ${ENVIRONMENT:-"Unknown"}
Virtual Environment: ${VIRTUAL_ENV:-"None"}
Database: ${DATABASE_URL:-"Not configured"}

Test Discovery:
--------------
Total Tests Found: $TOTAL_TESTS
├── Unit Tests: $UNIT_TESTS
├── Integration Tests: $INTEGRATION_TESTS  
├── Security Tests: $SECURITY_TESTS
└── End-to-End Tests: $E2E_TESTS

Test Execution Results:
----------------------
$TEST_RESULTS_STATUS

Code Coverage:
-------------
Coverage Achieved: $COVERAGE_PERCENT%
Coverage Threshold: $COVERAGE_THRESHOLD%
Status: $([ "${COVERAGE_PERCENT%.*}" -ge "${COVERAGE_THRESHOLD%.*}" ] 2>/dev/null && echo "PASSED" || echo "BELOW THRESHOLD")

Quality Checks:
--------------
$([ -f "reports/quality/quality_summary.txt" ] && echo "✓ Code quality analysis completed" || echo "✗ Code quality analysis not run")
$([ -f "reports/quality/mypy.txt" ] && echo "✓ Type checking completed" || echo "✗ Type checking not run")
$([ -f "reports/quality/bandit_report.html" ] && echo "✓ Security analysis completed" || echo "✗ Security analysis not run")
$([ -f "reports/quality/safety_report.txt" ] && echo "✓ Dependency scanning completed" || echo "✗ Dependency scanning not run")

Generated Reports:
-----------------
Main Reports:
- HTML Test Report: reports/test_report.html
- JSON Test Results: reports/test_results.json
- HTML Coverage Report: reports/coverage_html/index.html
- JSON Coverage Data: reports/coverage.json
- XML Coverage Data: reports/coverage.xml

Quality Reports:
- Code Quality Summary: reports/quality/quality_summary.txt
- MyPy Type Report: reports/quality/mypy_html/index.html
- Security Analysis: reports/quality/bandit_report.html
- Dependency Scan: reports/quality/safety_report.txt

Log Files:
- Execution Log: $LOG_FILE
- Quality Logs: reports/quality/

Commands to View Reports:
------------------------
# View test report in browser
open reports/test_report.html

# View coverage report in browser  
open reports/coverage_html/index.html

# View security report in browser
open reports/quality/bandit_report.html

# View type checking report in browser
open reports/quality/mypy_html/index.html

EOF

    print_success "Comprehensive test summary generated: reports/test_summary.txt"
    
    # Generate a dashboard
    print_section "Creating test dashboard"
    cat > reports/dashboard.html << EOF
<!DOCTYPE html>
<html>
<head>
    <title>ConvrseConnect Backend Test Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .card { background: white; padding: 20px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
        .metric { text-align: center; padding: 15px; }
        .metric h3 { margin: 0; color: #333; }
        .metric .value { font-size: 2em; font-weight: bold; color: #007cba; }
        .status-pass { color: #28a745; }
        .status-fail { color: #dc3545; }
        .status-warn { color: #ffc107; }
        h1 { color: #333; text-align: center; }
        .links { text-align: center; margin: 20px 0; }
        .links a { display: inline-block; margin: 0 10px; padding: 10px 20px; background: #007cba; color: white; text-decoration: none; border-radius: 4px; }
        .links a:hover { background: #005fa3; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 8px; text-align: center; margin-bottom: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 ConvrseConnect Backend Test Dashboard</h1>
            <p>Generated on $(date)</p>
        </div>
        
        <div class="grid">
            <div class="card">
                <div class="metric">
                    <h3>Total Tests</h3>
                    <div class="value">$TOTAL_TESTS</div>
                </div>
            </div>
            
            <div class="card">
                <div class="metric">
                    <h3>Code Coverage</h3>
                    <div class="value $([ "${COVERAGE_PERCENT%.*}" -ge "${COVERAGE_THRESHOLD%.*}" ] 2>/dev/null && echo "status-pass" || echo "status-fail")">$COVERAGE_PERCENT%</div>
                </div>
            </div>
            
            <div class="card">
                <div class="metric">
                    <h3>Unit Tests</h3>
                    <div class="value">$UNIT_TESTS</div>
                </div>
            </div>
            
            <div class="card">
                <div class="metric">
                    <h3>E2E Tests</h3>
                    <div class="value">$E2E_TESTS</div>
                </div>
            </div>
        </div>
        
        <div class="card">
            <h2>📊 Quick Links</h2>
            <div class="links">
                <a href="test_report.html">Test Results</a>
                <a href="coverage_html/index.html">Coverage Report</a>
                <a href="quality/bandit_report.html">Security Analysis</a>
                <a href="quality/mypy_html/index.html">Type Checking</a>
                <a href="dashboard.html">Dashboard</a>
            </div>
        </div>
        
        <div class="card">
            <h2>📈 Test Metrics</h2>
            <ul>
                <li><strong>Unit Tests:</strong> $UNIT_TESTS (Core functionality)</li>
                <li><strong>Integration Tests:</strong> $INTEGRATION_TESTS (Database interactions)</li>
                <li><strong>Security Tests:</strong> $SECURITY_TESTS (Authentication & authorization)</li>
                <li><strong>End-to-End Tests:</strong> $E2E_TESTS (Full workflows - BUILD CRITICAL)</li>
            </ul>
        </div>
        
        <div class="card">
            <h2>🎯 Build Status</h2>
            <p><strong>Coverage Threshold:</strong> $COVERAGE_THRESHOLD%</p>
            <p><strong>Current Coverage:</strong> $COVERAGE_PERCENT%</p>
            <p><strong>Critical Tests:</strong> Security Tests & E2E Tests must pass</p>
            <p><strong>Database:</strong> ${DATABASE_URL:-"Not configured"}</p>
        </div>
    </div>
</body>
</html>
EOF

    print_success "Test dashboard created: reports/dashboard.html"
    print_info "Open reports/dashboard.html in your browser for a visual overview"
}

# =============================================================================
# CLEANUP
# =============================================================================

cleanup() {
    print_banner "CLEANUP"
    
    # Clean up test databases
    rm -f test*.db 2>/dev/null || true
    print_info "Test databases removed"
    
    # Clean up temporary files
    find . -name "*.pyc" -delete 2>/dev/null || true
    find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    rm -rf .pytest_cache 2>/dev/null || true
    
    print_success "Cleanup completed"
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "🚀 ConvrseConnect Backend Comprehensive Test Runner"
    echo ""
    echo "Test Execution Options:"
    echo "  --unit          Run only unit tests"
    echo "  --integration   Run only integration tests"
    echo "  --security      Run only security tests"
    echo "  --e2e           Run only end-to-end tests"
    echo "  --performance   Run only performance tests"
    echo "  --parallel      Run tests in parallel"
    echo "  --coverage      Run all tests with coverage"
    echo "  --comprehensive Run all tests including edge cases"
    echo ""
    echo "Quality Assurance Options:"
    echo "  --quality       Run comprehensive code quality checks"
    echo "  --lint          Run linting only"
    echo "  --security-scan Run security scanning only"
    echo ""
    echo "Execution Options:"
    echo "  --fast          Skip environment setup (for CI)"
    echo "  --skip-quality  Skip code quality checks"
    echo "  --verbose       Enable verbose output"
    echo "  --help          Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                    # Run complete test suite"
    echo "  $0 --comprehensive    # Run all tests with quality checks"
    echo "  $0 --unit --coverage  # Run unit tests with coverage"
    echo "  $0 --e2e             # Run only E2E tests (build critical)"
    echo "  $0 --quality          # Run all quality checks"
    echo "  $0 --fast --parallel  # Fast parallel execution for CI"
    echo ""
    echo "Note: E2E and Security tests are build-critical and will fail the build if they fail"
}

main() {
    # Initialize log file
    > $LOG_FILE
    echo "Test execution started at $(date)" >> $LOG_FILE
    
    # Parse command line arguments
    SKIP_SETUP=false
    SKIP_QUALITY=false
    VERBOSE=false
    RUN_UNIT=false
    RUN_INTEGRATION=false
    RUN_SECURITY=false
    RUN_E2E=false
    RUN_PERFORMANCE=false
    RUN_PARALLEL=false
    RUN_COVERAGE=false
    RUN_QUALITY=false
    RUN_LINT=false
    RUN_SECURITY_SCAN=false
    RUN_COMPREHENSIVE=false
    RUN_ALL=true
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --unit)
                RUN_UNIT=true
                RUN_ALL=false
                shift
                ;;
            --integration)
                RUN_INTEGRATION=true
                RUN_ALL=false
                shift
                ;;
            --security)
                RUN_SECURITY=true
                RUN_ALL=false
                shift
                ;;
            --e2e)
                RUN_E2E=true
                RUN_ALL=false
                shift
                ;;
            --performance)
                RUN_PERFORMANCE=true
                RUN_ALL=false
                shift
                ;;
            --parallel)
                RUN_PARALLEL=true
                RUN_ALL=false
                shift
                ;;
            --coverage)
                RUN_COVERAGE=true
                RUN_ALL=false
                shift
                ;;
            --comprehensive)
                RUN_COMPREHENSIVE=true
                RUN_ALL=false
                shift
                ;;
            --quality)
                RUN_QUALITY=true
                RUN_ALL=false
                shift
                ;;
            --lint)
                RUN_LINT=true
                RUN_ALL=false
                shift
                ;;
            --security-scan)
                RUN_SECURITY_SCAN=true
                RUN_ALL=false
                shift
                ;;
            --fast)
                SKIP_SETUP=true
                shift
                ;;
            --skip-quality)
                SKIP_QUALITY=true
                shift
                ;;
            --verbose)
                VERBOSE=true
                shift
                ;;
            --help)
                show_usage
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
    
    # Start execution
    print_banner "CONVRSE CONNECT BACKEND TEST RUNNER"
    print_info "Starting comprehensive test execution..."
    echo "Timestamp: $(date)"
    echo "Working Directory: $(pwd)"
    echo ""
    
    # Track execution time
    START_TIME=$(date +%s)
    
    # Setup environment (unless skipped)
    if [ "$SKIP_SETUP" = false ]; then
        setup_environment
        setup_test_database
    else
        print_info "Skipping environment setup (--fast mode)"
        # Still need to set basic environment variables
        export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
        export ENVIRONMENT="test"
    fi
    
    # Exit code tracking
    EXIT_CODE=0
    
    # Set verbose output if requested
    if [ "$VERBOSE" = true ]; then
        set -x
        print_info "Verbose mode enabled"
    fi
    
    # Execute tests based on options
    if [ "$RUN_UNIT" = true ]; then
        run_unit_tests || EXIT_CODE=1
    elif [ "$RUN_INTEGRATION" = true ]; then
        run_integration_tests
    elif [ "$RUN_SECURITY" = true ]; then
        run_security_tests || EXIT_CODE=1
    elif [ "$RUN_E2E" = true ]; then
        run_e2e_tests || EXIT_CODE=1
    elif [ "$RUN_PERFORMANCE" = true ]; then
        run_performance_tests
    elif [ "$RUN_PARALLEL" = true ]; then
        run_tests_parallel || EXIT_CODE=1
    elif [ "$RUN_COVERAGE" = true ]; then
        run_all_tests_with_coverage || EXIT_CODE=1
    elif [ "$RUN_COMPREHENSIVE" = true ]; then
        # Run code quality first
        if [ "$SKIP_QUALITY" = false ]; then
            run_code_quality_checks
        fi
        run_comprehensive_tests || EXIT_CODE=1
        run_all_tests_with_coverage || EXIT_CODE=1
    elif [ "$RUN_QUALITY" = true ]; then
        run_code_quality_checks || EXIT_CODE=1
    elif [ "$RUN_LINT" = true ]; then
        black --check --diff src tests || EXIT_CODE=1
        isort --check-only --diff src tests || EXIT_CODE=1
        flake8 src tests --exclude=migrations,__pycache__,venv,.venv,.git || EXIT_CODE=1
    elif [ "$RUN_SECURITY_SCAN" = true ]; then
        mkdir -p reports/quality
        bandit -r src -f html -o reports/quality/bandit_report.html || EXIT_CODE=1
        safety check || EXIT_CODE=1
    elif [ "$RUN_ALL" = true ]; then
        # Run complete test suite
        print_banner "EXECUTING COMPLETE TEST SUITE"
        
        # Run quality checks unless skipped
        if [ "$SKIP_QUALITY" = false ]; then
            run_code_quality_checks
        fi
        
        # Run all tests
        run_comprehensive_tests || EXIT_CODE=1
        
        # Generate coverage report if tests passed
        if [ $EXIT_CODE -eq 0 ]; then
            print_banner "GENERATING COMPREHENSIVE COVERAGE REPORT"
            run_all_tests_with_coverage || EXIT_CODE=1
        fi
    fi
    
    # Generate reports
    generate_reports
    
    # Calculate execution time
    END_TIME=$(date +%s)
    EXECUTION_TIME=$((END_TIME - START_TIME))
    
    # Final status
    print_banner "TEST EXECUTION COMPLETE"
    
    if [ $EXIT_CODE -eq 0 ]; then
        print_success "🎉 All critical tests completed successfully!"
        print_info "Execution time: ${EXECUTION_TIME} seconds"
        print_info "📊 Test Reports:"
        print_info "   - Dashboard: reports/dashboard.html"
        print_info "   - Coverage: reports/coverage_html/index.html"
        print_info "   - Security: reports/quality/bandit_report.html"
        print_info "   - Summary: reports/test_summary.txt"
    else
        print_error "❌ Some critical tests failed!"
        print_info "Execution time: ${EXECUTION_TIME} seconds"
        print_info "Check $LOG_FILE for detailed error information"
        print_info "Review reports/ directory for analysis"
    fi
    
    # Cleanup
    cleanup
    
    echo "Test execution finished at $(date)" >> $LOG_FILE
    
    exit $EXIT_CODE
}

# Handle script interruption
trap cleanup EXIT INT TERM

# Run main function with all arguments
main "$@" 