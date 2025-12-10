# Test Coverage Summary

## Overview
- **Total Tests**: 64
- **Tests with Markers**: 3 (all marked as `@pytest.mark.integration`)
- **Tests without Markers**: 61 (deselected when running `pytest -m integration`)

## Test Breakdown by File

### Integration Tests (3 tests - marked with `@pytest.mark.integration`)
**File: `test_api_scenarios.py`**
- `test_revision_persisted_to_database` ✅
- `test_anonymous_revision_persisted_with_session_id` ✅
- `test_list_completed_runs` ✅

### Unit Tests (0 tests - **NONE marked with `@pytest.mark.unit`**)
**Note**: Many tests are unit tests but not marked as such:
- `test_file_processing.py` - 24 tests (file processing unit tests)
- `test_scoring_system.py` - 3 tests (scoring system unit tests)
- `test_backend_basic.py` - 4 tests (basic backend tests)
- `test_bootstrap.py` - 1 test (bootstrap test)
- `test_database.py` - 3 tests (database tests)
- `test_deployment.py` - 11 tests (deployment configuration tests)

### API Integration Tests (9 tests - **NOT marked**)
**File: `test_api_scenarios.py`**
- `test_health_endpoint` ✅
- `test_create_revision_basic` ✅
- `test_create_revision_with_files` ✅
- `test_start_run` ✅
- `test_get_questions` ✅
- `test_submit_answer` ✅
- `test_get_summary` ✅
- `test_full_workflow` ✅
- `test_marking_with_ai` ✅

### E2E Smoke Tests (8 tests - **NOT marked**)
**File: `test_e2e_smoke.py`**
- `test_health` ✅
- `test_create_revision_anonymous` ✅
- `test_list_revisions` ⚠️ (ERROR - setup issue)
- `test_start_run` ⚠️ (ERROR - setup issue)
- `test_get_question` ⚠️ (ERROR - setup issue)
- `test_submit_answer` ⚠️ (ERROR - setup issue)
- `test_get_summary` ⚠️ (ERROR - setup issue)
- `test_database_persistence` ⚠️ (ERROR - setup issue)

### File Processing Unit Tests (24 tests - **NOT marked**)
**File: `test_file_processing.py`**
- Image compression: 4 tests (3 ✅, 1 SKIPPED)
- PDF extraction: 3 tests (all ⚠️ FAILED)
- PPTX extraction: 2 tests (all ⚠️ FAILED)
- Image OCR: 4 tests (all ⚠️ FAILED)
- File processing: 7 tests (all ⚠️ FAILED)
- Constants: 2 tests (both ✅)

### Scoring System Tests (3 tests - **NOT marked**)
**File: `test_scoring_system.py`**
- `test_score_field_present` ✅
- `test_accuracy_calculation_with_partial_marks` ✅
- `test_score_values` ✅

## Issues Identified

### 1. Missing Markers
- **61 tests are not marked** with `@pytest.mark.unit` or `@pytest.mark.integration`
- When running `pytest -m integration`, only 3 tests run (the marked ones)
- When running `pytest -m unit`, 0 tests run (none are marked)

### 2. Test Failures
- **File Processing Tests**: 18 tests failing (likely due to missing mocks or dependencies)
- **E2E Tests**: 6 tests with setup errors (likely dependency chain issues)

### 3. Test Organization
- Unit tests should be marked with `@pytest.mark.unit`
- Integration tests should be marked with `@pytest.mark.integration`
- E2E tests could be marked with `@pytest.mark.e2e` (if added to markers)

## Recommendations

1. **Add markers to all tests**:
   - Mark unit tests in `test_file_processing.py`, `test_scoring_system.py`, etc. with `@pytest.mark.unit`
   - Mark API integration tests in `test_api_scenarios.py` with `@pytest.mark.integration`
   - Consider adding `@pytest.mark.e2e` for E2E tests

2. **Fix failing tests**:
   - Investigate file processing test failures
   - Fix E2E test setup errors

3. **Improve test organization**:
   - Follow the guidelines in `DEVELOPMENT_NOTES.md` for test categorization
   - Ensure all tests are properly marked for easy filtering

## Current Test Execution

```bash
# Run all tests
pytest  # Runs 64 tests (some fail)

# Run only integration tests (as currently marked)
pytest -m integration  # Runs 3 tests ✅

# Run only unit tests (as currently marked)
pytest -m unit  # Runs 0 tests ❌ (none marked)
```

