#!/opt/homebrew/bin/bash

# =============================================================================
# CONVRSE CONNECT BACKEND - COMPREHENSIVE TEST REPORT GENERATOR
# =============================================================================
# Generates detailed reports for unit tests, integration tests, security tests, 
# end-to-end tests, and coverage with beautiful formatting and statistics
# =============================================================================

set -e

# Ensure we're using bash 4.0+ for associative arrays
if [ "${BASH_VERSION%%.*}" -lt 4 ]; then
    echo "Error: This script requires Bash 4.0 or higher for associative arrays"
    exit 1
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m' # No Color

print_header() {
    echo -e "\n${CYAN}${BOLD}=================================================${NC}"
    echo -e "${CYAN}${BOLD} $1${NC}"
    echo -e "${CYAN}${BOLD}=================================================${NC}\n"
}

print_section() {
    echo -e "\n${BLUE}--- $1 ---${NC}"
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

# Setup environment
setup_environment() {
    # Activate virtual environment
    if [[ -f "venv/bin/activate" ]] && [[ -z "$VIRTUAL_ENV" ]]; then
        source venv/bin/activate
        print_info "Activated virtual environment"
    fi

    # Set environment variables
    export ENVIRONMENT=test
    export TESTING=true
    export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
    export DATABASE_URL="sqlite+aiosqlite:///./test_reports.db"
    export JWT_SECRET_KEY="test-secret-key-for-testing-only-at-least-32-chars"
    
    print_info "Environment configured for testing"
}

# Create reports directory structure
create_reports_structure() {
    mkdir -p reports/{unit,integration,security,e2e,api,performance}
    mkdir -p reports/coverage/{html,xml,json}
    mkdir -p reports/quality
    print_info "Created comprehensive reports directory structure"
}

print_header "CONVRSE CONNECT BACKEND - COMPREHENSIVE TEST REPORT GENERATION"

setup_environment
create_reports_structure

# Variables to track results using associative arrays (Bash 4.0+)
declare -A test_results
declare -A test_counts

# Initialize test results
test_results[unit]=""
test_results[integration]=""
test_results[security]=""
test_results[e2e]=""
test_results[api]=""
test_results[coverage]=""

# Initialize test counts
test_counts[unit]=0
test_counts[integration]=0
test_counts[security]=0
test_counts[e2e]=0
test_counts[api]=0

print_header "1. UNIT TESTS REPORT"
print_section "Running Unit Tests"
print_info "Testing core business logic and services..."

if python3 -m pytest tests/unit/ -v --tb=short \
    --junitxml=reports/unit/junit.xml \
    --html=reports/unit/report.html --self-contained-html \
    > reports/unit/unit_tests_detailed.txt 2>&1; then
    
    test_results[unit]="PASSED"
    print_success "Unit tests completed successfully"
    
    # Extract test count
    test_counts[unit]=$(grep -c "PASSED\|FAILED\|SKIPPED" reports/unit/unit_tests_detailed.txt || echo "0")
    
    echo "📄 Detailed report: reports/unit/unit_tests_detailed.txt"
    echo "📊 HTML report: reports/unit/report.html"
    echo "📋 JUnit XML: reports/unit/junit.xml"
    
    # Show summary
    echo -e "\n${CYAN}Unit Tests Summary:${NC}"
    grep -E "(PASSED|FAILED|SKIPPED|===.*===)" reports/unit/unit_tests_detailed.txt | tail -5
else
    test_results[unit]="FAILED"
    test_counts[unit]=$(grep -c "PASSED\|FAILED\|SKIPPED" reports/unit/unit_tests_detailed.txt || echo "0")
    print_error "Unit tests failed - check reports/unit/unit_tests_detailed.txt"
fi

print_header "2. INTEGRATION TESTS REPORT"
print_section "Running Integration Tests"
print_info "Testing database and service integrations..."

if python3 -m pytest tests/integration/ -v --tb=short -m integration \
    --junitxml=reports/integration/junit.xml \
    --html=reports/integration/report.html --self-contained-html \
    > reports/integration/integration_tests_detailed.txt 2>&1; then
    
    test_results[integration]="PASSED"
    print_success "Integration tests completed successfully"
    
    test_counts[integration]=$(grep -c "PASSED\|FAILED\|SKIPPED" reports/integration/integration_tests_detailed.txt || echo "0")
    
    echo "📄 Detailed report: reports/integration/integration_tests_detailed.txt"
    echo "📊 HTML report: reports/integration/report.html"
    
    # Show summary
    echo -e "\n${CYAN}Integration Tests Summary:${NC}"
    grep -E "(PASSED|FAILED|SKIPPED|===.*===)" reports/integration/integration_tests_detailed.txt | tail -5
else
    test_results[integration]="FAILED"
    test_counts[integration]=$(grep -c "PASSED\|FAILED\|SKIPPED" reports/integration/integration_tests_detailed.txt || echo "0")
    print_error "Integration tests failed - check reports/integration/integration_tests_detailed.txt"
fi

print_header "3. SECURITY TESTS REPORT"
print_section "Running Security Tests"
print_info "Testing authentication, authorization, and security controls..."

if python3 -m pytest tests/security/ -v --tb=short -m security \
    --junitxml=reports/security/junit.xml \
    --html=reports/security/report.html --self-contained-html \
    > reports/security/security_tests_detailed.txt 2>&1; then
    
    test_results[security]="PASSED"
    print_success "Security tests completed successfully"
    
    test_counts[security]=$(grep -c "PASSED\|FAILED\|SKIPPED" reports/security/security_tests_detailed.txt || echo "0")
    
    echo "📄 Detailed report: reports/security/security_tests_detailed.txt"
    echo "📊 HTML report: reports/security/report.html"
    
    # Show summary
    echo -e "\n${CYAN}Security Tests Summary:${NC}"
    grep -E "(PASSED|FAILED|SKIPPED|===.*===)" reports/security/security_tests_detailed.txt | tail -5
else
    test_results[security]="FAILED"
    test_counts[security]=$(grep -c "PASSED\|FAILED\|SKIPPED" reports/security/security_tests_detailed.txt || echo "0")
    print_error "Security tests failed - check reports/security/security_tests_detailed.txt"
fi

print_header "4. END-TO-END TESTS REPORT"
print_section "Running End-to-End Tests"
print_info "Testing complete workflows and user journeys..."

if python3 -m pytest tests/e2e/ -v --tb=short -m e2e \
    --junitxml=reports/e2e/junit.xml \
    --html=reports/e2e/report.html --self-contained-html \
    > reports/e2e/e2e_tests_detailed.txt 2>&1; then
    
    test_results[e2e]="PASSED"
    print_success "End-to-End tests completed successfully"
    
    test_counts[e2e]=$(grep -c "PASSED\|FAILED\|SKIPPED" reports/e2e/e2e_tests_detailed.txt || echo "0")
    
    echo "📄 Detailed report: reports/e2e/e2e_tests_detailed.txt"
    echo "📊 HTML report: reports/e2e/report.html"
    
    # Show summary
    echo -e "\n${CYAN}End-to-End Tests Summary:${NC}"
    grep -E "(PASSED|FAILED|SKIPPED|===.*===)" reports/e2e/e2e_tests_detailed.txt | tail -5
else
    test_results[e2e]="FAILED"
    test_counts[e2e]=$(grep -c "PASSED\|FAILED\|SKIPPED" reports/e2e/e2e_tests_detailed.txt || echo "0")
    print_error "End-to-End tests failed - check reports/e2e/e2e_tests_detailed.txt"
fi

print_header "5. COMPREHENSIVE COVERAGE REPORT"
print_section "Generating Coverage Analysis"
print_info "Analyzing code coverage across all test categories..."

if python3 -m pytest \
    --cov=src \
    --cov-report=term-missing \
    --cov-report=html:reports/coverage/html \
    --cov-report=xml:reports/coverage/coverage.xml \
    --cov-report=json:reports/coverage/coverage.json \
    --cov-fail-under=47 \
    -m "not integration and not security and not e2e" \
    --ignore=test_scripts/ \
    tests/ \
    > reports/coverage/coverage_detailed.txt 2>&1; then
    
    test_results[coverage]="PASSED"
    print_success "Coverage report generated successfully"
    
    echo "📄 Terminal report: reports/coverage/coverage_detailed.txt"
    echo "📊 HTML report: reports/coverage/html/index.html"
    echo "📊 XML report: reports/coverage/coverage.xml"
    echo "📊 JSON report: reports/coverage/coverage.json"
    
    # Extract coverage percentage
    coverage_percent=$(grep -o "TOTAL.*[0-9]\+%" reports/coverage/coverage_detailed.txt | grep -o "[0-9]\+%" | tail -1 || echo "N/A")
    
    # Show coverage summary
    echo -e "\n${CYAN}Coverage Summary:${NC}"
    echo "📈 Total Coverage: ${GREEN}$coverage_percent${NC}"
    grep -A 15 "Name.*Stmts.*Miss.*Cover" reports/coverage/coverage_detailed.txt | head -20
else
    test_results[coverage]="FAILED"
    coverage_percent="N/A"
    print_error "Coverage report generation failed"
fi

print_header "6. API TESTS BREAKDOWN"
print_section "Running API-specific tests"
print_info "Testing REST API endpoints and responses..."

if python3 -m pytest -v -k "api" --tb=short \
    --html=reports/api/report.html --self-contained-html \
    > reports/api/api_tests_detailed.txt 2>&1; then
    
    test_results[api]="PASSED"
    print_success "API tests completed successfully"
    
    test_counts[api]=$(grep -c "PASSED\|FAILED\|SKIPPED" reports/api/api_tests_detailed.txt || echo "0")
    
    echo "📄 Detailed report: reports/api/api_tests_detailed.txt"
    echo "📊 HTML report: reports/api/report.html"
    
    # Count API tests by category
    echo -e "\n${CYAN}API Tests Breakdown:${NC}"
    echo "• Project API: $(grep -c "test.*project.*api" reports/api/api_tests_detailed.txt || echo "0") tests"
    echo "• Deliverable API: $(grep -c "test.*deliverable.*api" reports/api/api_tests_detailed.txt || echo "0") tests"
    echo "• Task API: $(grep -c "test.*task.*api" reports/api/api_tests_detailed.txt || echo "0") tests"
    echo "• Review API: $(grep -c "test.*review.*api" reports/api/api_tests_detailed.txt || echo "0") tests"
else
    test_results[api]="FAILED"
    test_counts[api]="0"
    print_error "API tests failed"
fi

print_header "7. OVERALL TEST SUMMARY & STATISTICS"

# Generate overall summary
echo -e "${CYAN}${BOLD}📊 COMPLETE TEST STATISTICS${NC}"
echo "======================================"

# Calculate test counts
total_unit=${test_counts[unit]:-0}
total_integration=${test_counts[integration]:-0}
total_security=${test_counts[security]:-0}
total_e2e=${test_counts[e2e]:-0}
total_api=${test_counts[api]:-0}

total_tests=$((total_unit + total_integration + total_security + total_e2e + total_api))

echo "📈 Total Tests Executed: ${BOLD}$total_tests${NC}"
echo "🔧 Unit Tests: $total_unit"
echo "🔗 Integration Tests: $total_integration"
echo "🔒 Security Tests: $total_security"
echo "🌍 End-to-End Tests: $total_e2e"
echo "🌐 API Tests: $total_api"

echo -e "\n${CYAN}${BOLD}📋 TEST RESULTS SUMMARY${NC}"
echo "========================="

# Function to print test result with appropriate color
print_test_result() {
    local category=$1
    local icon=$2
    local result=${test_results[$category]:-"UNKNOWN"}
    
    case $result in
        "PASSED")
            echo -e "$icon $category: ${GREEN}${BOLD}PASSED${NC}"
            ;;
        "FAILED")
            echo -e "$icon $category: ${RED}${BOLD}FAILED${NC}"
            ;;
        "SKIPPED")
            echo -e "$icon $category: ${YELLOW}${BOLD}SKIPPED${NC}"
            ;;
        *)
            echo -e "$icon $category: ${YELLOW}${BOLD}UNKNOWN${NC}"
            ;;
    esac
}

print_test_result "unit" "🔧 Unit Tests"
print_test_result "integration" "🔗 Integration Tests"
print_test_result "security" "🔒 Security Tests"
print_test_result "e2e" "🌍 End-to-End Tests"
print_test_result "api" "🌐 API Tests"
print_test_result "coverage" "📊 Coverage Report"

if [[ "${test_results[coverage]}" == "PASSED" ]]; then
    echo -e "📈 Code Coverage: ${GREEN}${BOLD}$coverage_percent${NC}"
fi

echo -e "\n${CYAN}${BOLD}🗂️  GENERATED REPORTS${NC}"
echo "========================="
echo "📁 Reports Directory Structure:"
echo "├── 📄 Unit Tests: reports/unit/"
echo "│   ├── unit_tests_detailed.txt"
echo "│   ├── report.html"
echo "│   └── junit.xml"
echo "├── 📄 Integration Tests: reports/integration/"
echo "│   ├── integration_tests_detailed.txt"
echo "│   ├── report.html"
echo "│   └── junit.xml"
echo "├── 📄 Security Tests: reports/security/"
echo "│   ├── security_tests_detailed.txt"
echo "│   ├── report.html"
echo "│   └── junit.xml"
echo "├── 📄 E2E Tests: reports/e2e/"
echo "│   ├── e2e_tests_detailed.txt"
echo "│   ├── report.html"
echo "│   └── junit.xml"
echo "├── 📄 API Tests: reports/api/"
echo "│   ├── api_tests_detailed.txt"
echo "│   └── report.html"
echo "└── 📊 Coverage Reports: reports/coverage/"
echo "    ├── coverage_detailed.txt"
echo "    ├── html/index.html"
echo "    ├── coverage.xml"
echo "    └── coverage.json"

print_header "8. TEST CATEGORIES & MARKERS BREAKDOWN"

echo -e "${CYAN}${BOLD}🏷️  Test Markers Used:${NC}"
echo "• @pytest.mark.unit - Unit tests for business logic"
echo "• @pytest.mark.integration - Database and service integration tests"
echo "• @pytest.mark.security - Authentication and security tests"
echo "• @pytest.mark.e2e - End-to-end workflow tests"
echo "• @pytest.mark.api - REST API endpoint tests"
echo "• @pytest.mark.auth - Authentication specific tests"
echo "• @pytest.mark.database - Database interaction tests"
echo "• @pytest.mark.validation - Input validation tests"

echo -e "\n${CYAN}${BOLD}🔒 Security Test Categories:${NC}"
echo "• Authentication & Authorization Security"
echo "• JWT Token Validation & Security"
echo "• Input Validation & Sanitization"
echo "• Rate Limiting & DoS Protection"
echo "• Security Headers & CORS"
echo "• Data Exposure Protection"
echo "• Circuit Breaker Security"

echo -e "\n${CYAN}${BOLD}🔗 Integration Test Categories:${NC}"
echo "• API Endpoint Integration"
echo "• Database Operations Integration"
echo "• Service Layer Integration"
echo "• Middleware Integration"
echo "• Event Bus Integration"
echo "• External Service Integration"

echo -e "\n${CYAN}${BOLD}🌍 End-to-End Test Categories:${NC}"
echo "• Complete Project Lifecycle"
echo "• Multi-User Collaboration Workflows"
echo "• Client Feedback Workflows"
echo "• Task Management Workflows"
echo "• Error Recovery & Resilience"

# Calculate overall success rate
success_count=0
total_categories=5

[[ "${test_results[unit]}" == "PASSED" ]] && ((success_count++))
[[ "${test_results[integration]}" == "PASSED" ]] && ((success_count++))
[[ "${test_results[security]}" == "PASSED" ]] && ((success_count++))
[[ "${test_results[e2e]}" == "PASSED" ]] && ((success_count++))
[[ "${test_results[coverage]}" == "PASSED" ]] && ((success_count++))

success_rate=$((success_count * 100 / total_categories))

echo -e "\n${CYAN}${BOLD}🎯 OVERALL SUCCESS RATE: ${GREEN}${BOLD}$success_rate%${NC} ($success_count/$total_categories categories passed)"

# Build status assessment
critical_failed=false
[[ "${test_results[unit]}" == "FAILED" ]] && critical_failed=true
[[ "${test_results[security]}" == "FAILED" ]] && critical_failed=true
[[ "${test_results[e2e]}" == "FAILED" ]] && critical_failed=true

if [[ "$critical_failed" == "true" ]]; then
    echo -e "\n${RED}${BOLD}🚨 BUILD CRITICAL TESTS FAILED!${NC}"
    echo -e "${RED}❌ Unit, Security, or E2E tests have failed - build should not proceed${NC}"
elif [[ $success_rate -eq 100 ]]; then
    echo -e "\n${GREEN}${BOLD}🎉 ALL TESTS COMPLETED SUCCESSFULLY!${NC}"
    echo -e "${GREEN}✨ ConvrseConnect Backend is ready for deployment!${NC}"
else
    echo -e "\n${YELLOW}${BOLD}⚠️  Some test categories failed, but build can proceed${NC}"
    echo -e "${YELLOW}📋 Review the failed categories and address issues when possible${NC}"
fi

print_header "9. DETAILED ANALYSIS & RECOMMENDATIONS"

echo -e "${CYAN}${BOLD}📈 CODE QUALITY METRICS${NC}"
echo "========================"

if [[ "${test_results[coverage]}" == "PASSED" && "$coverage_percent" != "N/A" ]]; then
    coverage_num=${coverage_percent%\%}
    if [[ $coverage_num -ge 80 ]]; then
        echo -e "📊 Coverage Status: ${GREEN}EXCELLENT${NC} ($coverage_percent)"
    elif [[ $coverage_num -ge 60 ]]; then
        echo -e "📊 Coverage Status: ${YELLOW}GOOD${NC} ($coverage_percent)"
    else
        echo -e "📊 Coverage Status: ${RED}NEEDS IMPROVEMENT${NC} ($coverage_percent)"
    fi
else
    echo -e "📊 Coverage Status: ${RED}UNAVAILABLE${NC}"
fi

echo -e "\n${CYAN}${BOLD}🎯 RECOMMENDATIONS${NC}"
echo "==================="

if [[ "${test_results[unit]}" == "FAILED" ]]; then
    echo -e "${RED}🔧 CRITICAL: Fix failing unit tests immediately${NC}"
fi

if [[ "${test_results[security]}" == "FAILED" ]]; then
    echo -e "${RED}🔒 CRITICAL: Address security test failures before deployment${NC}"
fi

if [[ "${test_results[e2e]}" == "FAILED" ]]; then
    echo -e "${RED}🌍 CRITICAL: Fix end-to-end test failures - core workflows broken${NC}"
fi

if [[ "${test_results[integration]}" == "FAILED" ]]; then
    echo -e "${YELLOW}🔗 WARNING: Integration test failures may indicate service communication issues${NC}"
fi

if [[ "${test_results[coverage]}" == "FAILED" || "$coverage_percent" == "N/A" ]]; then
    echo -e "${YELLOW}📊 IMPROVEMENT: Increase test coverage to improve code quality${NC}"
fi

echo -e "\n${GREEN}✅ Keep test coverage above 60%${NC}"
echo -e "${GREEN}✅ Ensure all security tests pass before deployment${NC}"
echo -e "${GREEN}✅ Monitor integration test stability${NC}"
echo -e "${GREEN}✅ Regularly run end-to-end tests in staging${NC}"

print_header "REPORT GENERATION COMPLETE"

echo -e "🌐 ${CYAN}Open the following reports in your browser:${NC}"
echo -e "   • Coverage: ${BOLD}open reports/coverage/html/index.html${NC}"
echo -e "   • Unit Tests: ${BOLD}open reports/unit/report.html${NC}"
echo -e "   • Security Tests: ${BOLD}open reports/security/report.html${NC}"
echo -e "   • E2E Tests: ${BOLD}open reports/e2e/report.html${NC}"

echo -e "\n📁 ${CYAN}All detailed reports are saved in the ${BOLD}reports/${NC}${CYAN} directory.${NC}"
echo -e "📋 ${CYAN}Use these reports for CI/CD integration and quality tracking.${NC}"

# Generate a summary JSON for CI/CD integration
cat > reports/test_summary.json << EOF
{
  "timestamp": "$(date -Iseconds)",
  "total_tests": $total_tests,
  "success_rate": $success_rate,
  "coverage_percentage": "$coverage_percent",
  "test_results": {
    "unit": "${test_results[unit]:-UNKNOWN}",
    "integration": "${test_results[integration]:-UNKNOWN}",
    "security": "${test_results[security]:-UNKNOWN}",
    "e2e": "${test_results[e2e]:-UNKNOWN}",
    "api": "${test_results[api]:-UNKNOWN}",
    "coverage": "${test_results[coverage]:-UNKNOWN}"
  },
  "test_counts": {
    "unit": $total_unit,
    "integration": $total_integration,
    "security": $total_security,
    "e2e": $total_e2e,
    "api": $total_api
  },
  "build_critical_failed": $critical_failed
}
EOF

print_info "Test summary JSON generated: reports/test_summary.json"

# Exit with appropriate code
if [[ "$critical_failed" == "true" ]]; then
    exit 1
else
    exit 0
fi 