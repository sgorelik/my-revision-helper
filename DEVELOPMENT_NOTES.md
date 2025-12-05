# Development Notes

## AI Assistant Optimization Preferences

### File Reading Optimization
To reduce token usage while maintaining quality, skip unnecessary file reads when:

- **Git operations**: Use `git status`, `git diff --stat` instead of reading files
- **Code search**: Use `grep` or `codebase_search` to find specific patterns
- **Understanding changes**: Use `git diff` or file metadata instead of full reads
- **Debugging**: Read only relevant sections, not entire files
- **Context available**: Rely on conversation history/summaries when sufficient

Read files when:
- User explicitly asks to review/read something
- Need to understand complex logic to make changes
- Error debugging requires full context
- Making code changes that need exact structure
- Quality would suffer without reading (refactoring, complex logic changes)

### General Principles
- Minimize token usage without sacrificing output quality
- Use tool outputs (git, grep, etc.) instead of reading files when possible
- Read files only when necessary for the task at hand

## Testing Policy

### When to Add Tests to Test Suite
When running Python scripts to test things out, **automatically add them as proper unit or integration tests** in the testing library (pytest) instead of creating standalone scripts.

### Test Organization

**Unit Tests** (`test_*.py` with `@pytest.mark.unit`):
- Test individual functions/modules in isolation
- Fast, no external dependencies
- Use mocks for external services (OpenAI, database, etc.)
- Example: `test_file_processing.py`

**Integration Tests** (`test_*.py` with `@pytest.mark.integration`):
- Test multiple components working together
- May require external services (database, API server)
- Test full workflows/end-to-end scenarios
- Example: `test_api_scenarios.py`

**E2E Tests** (`test_*.py` with `@pytest.mark.integration` or `@pytest.mark.e2e`):
- Test complete user flows
- Require full stack running (API server, database)
- Can be slower, may require setup/teardown
- Example: `test_e2e_smoke.py` (should be converted to pytest)

### Test File Naming
- Unit tests: `test_<module_name>.py` (e.g., `test_file_processing.py`)
- Integration tests: `test_<feature>_scenarios.py` (e.g., `test_api_scenarios.py`)
- E2E tests: `test_e2e_<feature>.py` (e.g., `test_e2e_smoke.py`)

### Pytest Markers
Use appropriate markers from `pyproject.toml`:
- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.slow` - Slow-running tests
- `@pytest.mark.requires_openai` - Tests requiring OpenAI API key
- `@pytest.mark.requires_pil` - Tests requiring PIL/Pillow

### Running Tests
```bash
# Run all tests
pytest

# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Run tests excluding slow ones
pytest -m "not slow"

# Run specific test file
pytest test_file_processing.py
```

### Guidelines
1. **Always use pytest** - Convert standalone scripts to pytest tests
2. **Use fixtures** - For setup/teardown (database, test clients, etc.)
3. **Mark appropriately** - Use markers to categorize tests
4. **Keep tests fast** - Unit tests should be very fast, integration tests can be slower
5. **Mock external services** - Don't hit real APIs in unit tests
6. **Clean up** - Use fixtures or teardown to clean test data

### Converting Standalone Scripts
When you create a standalone test script (e.g., `test_something.py` with `if __name__ == "__main__"`), convert it to pytest format:

**Before (standalone):**
```python
def test_thing():
    # test code
    assert something

if __name__ == "__main__":
    test_thing()
```

**After (pytest):**
```python
import pytest

@pytest.mark.unit  # or @pytest.mark.integration
def test_thing():
    # test code
    assert something
```

Then run with `pytest test_something.py` instead of `python test_something.py`

