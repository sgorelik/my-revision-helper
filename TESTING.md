# Testing Guide

This document outlines the testing strategy, conventions, and best practices for the My Revision Helper project.

## Test Structure

### Test Files
- **Unit Tests**: `test_*.py` files in the root directory
  - `test_file_processing.py` - File processing unit tests
  - `test_scoring_system.py` - Scoring system tests
  - `test_deployment.py` - Deployment configuration tests
  - `test_bootstrap.py` - Bootstrap/initialization tests

- **Integration Tests**: `test_api_scenarios.py`
  - Full API workflow tests
  - End-to-end scenario testing

- **E2E Tests**: `frontend/e2e/*.spec.ts`
  - Playwright browser tests
  - See `README_TESTING.md` for details

## Running Tests

### All Tests
```bash
# Run all Python tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest test_api_scenarios.py

# Run specific test
pytest test_api_scenarios.py::test_submit_answer
```

### Test Categories
```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Skip slow tests
pytest -m "not slow"

# Run tests that require OpenAI (if API key is set)
pytest -m requires_openai
```

### E2E Tests
```bash
cd frontend
npm run test:e2e
```

## Test Configuration

### Pytest Configuration
Pytest is configured in `pyproject.toml` under `[tool.pytest.ini_options]`:

- **Test Discovery**: Automatically finds `test_*.py` files
- **Markers**: Use markers to categorize tests (`@pytest.mark.integration`, etc.)
- **Async Support**: Auto-detects async tests with `asyncio_mode = "auto"`

### Environment Variables
Some tests require environment variables:
- `OPENAI_API_KEY` - Required for AI-related tests (marked with `@pytest.mark.requires_openai`)
- `TEMPORAL_TARGET` - Optional, for Temporal workflow tests
- `PLAYWRIGHT_BASE_URL` - Optional, for E2E tests (defaults to `http://localhost:8000`)

## Writing Tests

### Test Naming Conventions
- Test files: `test_*.py` or `*_test.py`
- Test classes: `Test*` (e.g., `TestFileProcessing`)
- Test functions: `test_*` (e.g., `test_submit_answer`)

### Test Structure
```python
import pytest
from my_revision_helper.api import app
from fastapi.testclient import TestClient

client = TestClient(app)

def test_example():
    """Test description explaining what is being tested."""
    # Arrange
    # Act
    # Assert
    assert result == expected
```

### Using Markers
```python
@pytest.mark.integration
def test_full_workflow():
    """Integration test for complete workflow."""
    pass

@pytest.mark.requires_openai
def test_ai_marking():
    """Test that requires OpenAI API key."""
    pass

@pytest.mark.asyncio
async def test_async_function():
    """Async test function."""
    pass
```

### Best Practices

1. **Test Independence**: Each test should be independent and not rely on other tests
2. **Clear Names**: Test names should clearly describe what is being tested
3. **Arrange-Act-Assert**: Structure tests with clear sections
4. **Use Fixtures**: Share setup code using pytest fixtures
5. **Mock External Services**: Mock OpenAI, file system, etc. in unit tests
6. **Test Edge Cases**: Include tests for error conditions and edge cases
7. **Keep Tests Fast**: Unit tests should run quickly (< 1 second each)
8. **Documentation**: Add docstrings explaining what each test validates

### Example Test with Fixtures
```python
import pytest
from unittest.mock import Mock, patch

@pytest.fixture
def mock_openai_client():
    """Fixture providing a mocked OpenAI client."""
    with patch('my_revision_helper.api.get_openai_client') as mock:
        yield mock

def test_with_mock(mock_openai_client):
    """Test using mocked OpenAI client."""
    mock_openai_client.return_value = Mock()
    # Test code here
```

## Test Coverage

### Current Coverage
- ✅ API endpoints (integration tests)
- ✅ Scoring system (unit + integration)
- ✅ File processing (unit tests)
- ✅ Deployment configuration
- ✅ E2E workflows (Playwright)

### Areas Needing More Tests
- [ ] More edge cases for file processing
- [ ] Error handling scenarios
- [ ] Temporal workflow tests
- [ ] Performance tests

## Continuous Integration

### Running Tests in CI
```bash
# Install dependencies
pip install -r requirements.txt
pip install pytest pytest-asyncio

# Run all tests
pytest

# Run with coverage (if configured)
pytest --cov=my_revision_helper --cov-report=html
```

### Test Requirements
- Python 3.12+
- pytest
- pytest-asyncio (for async tests)
- fastapi[test] (for TestClient)
- Optional: OpenAI API key for AI tests

## Troubleshooting

### Common Issues

**Tests fail with "Unknown pytest.mark.asyncio"**
- Install pytest-asyncio: `pip install pytest-asyncio`
- Ensure it's imported in test files: `import pytest_asyncio`

**Async tests not running**
- Check `asyncio_mode = "auto"` in `pyproject.toml`
- Use `@pytest.mark.asyncio` decorator

**Tests requiring OpenAI fail**
- Set `OPENAI_API_KEY` environment variable
- Or skip with: `pytest -m "not requires_openai"`

**File processing tests fail**
- Ensure required libraries are installed: `pdfplumber`, `python-pptx`, `Pillow`
- Check test mocks are set up correctly

## Test Maintenance

### Adding New Tests
1. Create test file following naming convention
2. Add appropriate markers
3. Follow Arrange-Act-Assert pattern
4. Add docstring explaining test purpose
5. Run tests locally before committing

### Updating Test Rules
- **Pytest configuration**: Edit `[tool.pytest.ini_options]` in `pyproject.toml`
- **Test conventions**: Update this document
- **CI/CD**: Update CI configuration files (if any)

## Related Documentation
- `README_TESTING.md` - E2E testing with Playwright
- `ARCHITECTURE.md` - System architecture
- `README.md` - Project overview

