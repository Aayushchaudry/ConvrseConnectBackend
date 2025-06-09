# ConvrseConnectBackend Test Suite

This directory contains comprehensive test suites for the ConvrseConnectBackend project, covering unit tests, integration tests, security tests, and end-to-end tests.

## Test Structure

```
tests/
├── conftest.py                 # Global test configuration and fixtures
├── unit/                       # Unit tests - fast, isolated tests
│   ├── test_models.py         # Model unit tests
│   └── test_services.py       # Service unit tests
├── integration/               # Integration tests - component interactions
│   ├── test_services.py      # Service integration tests
│   └── test_api_endpoints.py # API integration tests
├── security/                  # Security tests
│   └── test_authentication.py # Authentication and authorization tests
├── e2e/                       # End-to-end tests
│   ├── test_complete_workflows.py # Complete workflow tests
│   └── test_api.py           # API workflow tests
└── README.md                  # This file
```

## Test Categories

### 🔧 Unit Tests (`tests/unit/`)
- **Purpose**: Test individual components in isolation
- **Speed**: Fast (< 1 second per test)
- **Scope**: Models, services, utilities
- **Mocking**: Heavy use of mocks for external dependencies
- **Coverage**: Aim for 90%+ code coverage

**Examples:**
- Model validation and business logic
- Service method functionality
- Utility function behavior
- Error handling and edge cases

### 🔗 Integration Tests (`tests/integration/`)
- **Purpose**: Test component interactions and database operations
- **Speed**: Medium (1-10 seconds per test)
- **Scope**: Service-to-database, API endpoints, event handling
- **Database**: Uses test database with real transactions
- **Coverage**: Focus on integration points

**Examples:**
- Service methods with actual database operations
- API endpoints with request/response validation
- Event publishing and handling
- Cross-service communication

### 🔒 Security Tests (`tests/security/`)
- **Purpose**: Test security mechanisms and vulnerability prevention
- **Speed**: Medium (1-5 seconds per test)
- **Scope**: Authentication, authorization, input validation
- **Focus**: Security vulnerabilities and attack prevention

**Examples:**
- Authentication token validation
- Authorization and access control
- SQL injection prevention
- XSS and CSRF protection
- Rate limiting and abuse prevention

### 🎯 End-to-End Tests (`tests/e2e/`)
- **Purpose**: Test complete user workflows and business processes
- **Speed**: Slow (10-60 seconds per test)
- **Scope**: Full application workflows
- **Database**: Uses test database with complete data setup
- **Coverage**: Business process validation

**Examples:**
- Complete project lifecycle (creation to delivery)
- Multi-user collaboration workflows
- Client feedback and revision cycles
- Error recovery scenarios

## Running Tests

### Prerequisites

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install pytest pytest-asyncio pytest-cov httpx
   ```

2. **Set Up Test Database**:
   ```bash
   # Create test database
   createdb test_project_db
   
   # Set environment variables
   export DATABASE_URL="postgresql+asyncpg://test_user:test_pass@localhost:5433/test_project_db"
   export ENV="test"
   ```

3. **Start Required Services**:
   ```bash
   # Start Kafka (if using)
   docker run -d --name kafka -p 9092:9092 confluentinc/cp-kafka
   
   # Start Redis (if using)
   docker run -d --name redis -p 6379:6379 redis:alpine
   ```

### Quick Start

```bash
# Run all tests with the comprehensive test runner
python run_tests.py

# Run only unit tests
python run_tests.py --no-integration --no-security --no-e2e

# Run quick test suite (unit + integration only)
python run_tests.py --quick

# Run full test suite including performance tests
python run_tests.py --full
```

### Manual Test Execution

```bash
# Run specific test categories
pytest tests/unit/ -m unit -v
pytest tests/integration/ -m integration -v
pytest tests/security/ -m security -v
pytest tests/e2e/ -m e2e -v

# Run with coverage
pytest tests/unit/ --cov=src --cov-report=html

# Run specific test files
pytest tests/unit/test_models.py -v
pytest tests/integration/test_api_endpoints.py -v

# Run specific test methods
pytest tests/unit/test_models.py::TestProjectModel::test_project_creation -v
```

### Test Markers

Use pytest markers to run specific test types:

```bash
# Run only unit tests
pytest -m unit

# Run only security tests
pytest -m security

# Run only slow tests
pytest -m slow

# Run tests excluding slow ones
pytest -m "not slow"

# Run API-related tests
pytest -m api

# Run database tests
pytest -m database
```

## Test Configuration

### Environment Variables

Set these environment variables for testing:

```bash
export ENV=test
export DEBUG=true
export DATABASE_URL=postgresql+asyncpg://test_user:test_pass@localhost:5433/test_project_db
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
export ACTIVE_EVENT_BUS=kafka
```

### Pytest Configuration

The test suite uses `pytest.ini` for configuration:

- **Test Discovery**: Automatically finds test files matching `test_*.py`
- **Markers**: Predefined markers for test categorization
- **Coverage**: Configured for 80% minimum coverage
- **Asyncio**: Automatic async test handling
- **Timeouts**: 5-minute timeout for long-running tests

### Fixtures

Global fixtures are defined in `conftest.py`:

- `test_engine`: Test database engine
- `db_session`: Database session for each test
- `test_client`: FastAPI test client
- `mock_event_bus`: Mocked event bus
- `mock_auth_client`: Mocked authentication client
- `test_project`: Sample project for testing
- `test_deliverable`: Sample deliverable for testing

## Writing Tests

### Unit Test Example

```python
@pytest.mark.unit
class TestProjectService:
    async def test_create_project(self, project_service, mock_event_bus):
        """Test project creation."""
        project_data = {
            "name": "Test Project",
            "budget": 50000.00
        }
        
        project = await project_service.create_project(**project_data)
        
        assert project.name == project_data["name"]
        assert project.budget == project_data["budget"]
        mock_event_bus.publish.assert_called_once()
```

### Integration Test Example

```python
@pytest.mark.integration
class TestProjectAPI:
    async def test_create_project_endpoint(self, test_client, auth_headers):
        """Test project creation via API."""
        project_data = {
            "name": "API Test Project",
            "budget": 75000.00
        }
        
        response = await test_client.post(
            "/api/v1/projects/",
            json=project_data,
            headers=auth_headers
        )
        
        assert response.status_code == 201
        assert response.json()["name"] == project_data["name"]
```

### Security Test Example

```python
@pytest.mark.security
class TestAuthentication:
    async def test_invalid_token_rejected(self, test_client):
        """Test that invalid tokens are rejected."""
        headers = {"Authorization": "Bearer invalid_token"}
        
        response = await test_client.get("/api/v1/projects/", headers=headers)
        
        assert response.status_code == 401
```

### E2E Test Example

```python
@pytest.mark.e2e
class TestProjectLifecycle:
    async def test_complete_project_workflow(self, test_client, auth_headers):
        """Test complete project lifecycle."""
        # 1. Create project
        project_response = await test_client.post("/api/v1/projects/", ...)
        project_id = project_response.json()["id"]
        
        # 2. Create deliverables
        deliverable_response = await test_client.post("/api/v1/deliverables/", ...)
        
        # 3. Complete workflow...
        # ... (full workflow implementation)
        
        # Final verification
        final_response = await test_client.get(f"/api/v1/projects/{project_id}")
        assert final_response.json()["status"] == "completed"
```

## Test Data Management

### Fixtures for Test Data

Use fixtures to create consistent test data:

```python
@pytest.fixture
async def test_project(db_session):
    """Create a test project."""
    project = Project(
        name="Test Project",
        budget=50000.00,
        business_id=1,
        created_by=1
    )
    db_session.add(project)
    await db_session.commit()
    yield project
    await db_session.delete(project)
    await db_session.commit()
```

### Database Cleanup

Tests automatically clean up database changes:

- Each test gets a fresh database session
- Transactions are rolled back after each test
- Fixtures handle cleanup of created objects

## Coverage Reporting

### Generate Coverage Reports

```bash
# Run tests with coverage
pytest --cov=src --cov-report=html --cov-report=term-missing

# View HTML coverage report
open htmlcov/index.html
```

### Coverage Targets

- **Unit Tests**: 90%+ coverage
- **Integration Tests**: 80%+ coverage
- **Overall**: 80%+ coverage
- **Critical Paths**: 95%+ coverage

## Continuous Integration

### GitHub Actions

The test suite integrates with CI/CD:

```yaml
name: Test Suite
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.9
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run tests
        run: python run_tests.py --full
```

### Pre-commit Hooks

Set up pre-commit hooks to run tests before commits:

```bash
# Install pre-commit
pip install pre-commit

# Set up hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

## Performance Testing

### Load Testing

```bash
# Run performance tests
pytest -m slow -v

# Run with performance profiling
pytest --profile-svg tests/performance/
```

### Benchmarking

Use `pytest-benchmark` for performance benchmarks:

```python
def test_service_performance(benchmark, service):
    """Benchmark service performance."""
    result = benchmark(service.expensive_operation)
    assert result is not None
```

## Troubleshooting

### Common Issues

1. **Database Connection Errors**:
   ```bash
   # Check database is running
   pg_isready -h localhost -p 5433
   
   # Verify connection string
   echo $DATABASE_URL
   ```

2. **Import Errors**:
   ```bash
   # Add project root to Python path
   export PYTHONPATH="${PYTHONPATH}:$(pwd)"
   ```

3. **Async Test Issues**:
   ```bash
   # Install pytest-asyncio
   pip install pytest-asyncio
   
   # Check pytest.ini has asyncio_mode = auto
   ```

4. **Fixture Scope Issues**:
   - Use `session` scope for expensive setup
   - Use `function` scope for test isolation
   - Use `module` scope for shared test data

### Debug Mode

Run tests in debug mode:

```bash
# Run with debug output
pytest -v -s --tb=long

# Run single test with debugging
pytest tests/unit/test_models.py::TestProjectModel::test_creation -v -s --pdb
```

## Best Practices

### Test Organization

1. **One test class per component**
2. **Descriptive test names**
3. **Arrange-Act-Assert pattern**
4. **Independent tests** (no test dependencies)
5. **Appropriate test markers**

### Test Data

1. **Use fixtures for setup**
2. **Clean up after tests**
3. **Avoid hardcoded values**
4. **Use factories for complex objects**
5. **Isolate test data**

### Assertions

1. **Specific assertions** (not just `assert True`)
2. **Multiple assertions per test** when appropriate
3. **Custom error messages** for clarity
4. **Test both positive and negative cases**
5. **Edge case testing**

### Performance

1. **Fast unit tests** (< 1 second)
2. **Reasonable integration tests** (< 10 seconds)
3. **Parallel test execution** when possible
4. **Mock external dependencies**
5. **Database transaction rollback**

## Contributing

### Adding New Tests

1. **Choose appropriate test category**
2. **Follow naming conventions**
3. **Add appropriate markers**
4. **Include docstrings**
5. **Update this README if needed**

### Test Review Checklist

- [ ] Tests are in the correct directory
- [ ] Appropriate markers are used
- [ ] Tests are independent
- [ ] Good test coverage
- [ ] Clear test names and documentation
- [ ] Proper cleanup and teardown
- [ ] No hardcoded values
- [ ] Edge cases covered

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [SQLAlchemy Testing](https://docs.sqlalchemy.org/en/14/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites)
- [Async Testing with pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [Security Testing Best Practices](https://owasp.org/www-project-web-security-testing-guide/) 