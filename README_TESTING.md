# End-to-End Testing Guide

This project uses [Playwright](https://playwright.dev/) for end-to-end (E2E) smoke tests to ensure critical user flows continue to work after UI changes.

## Quick Start

### Prerequisites

1. **Backend server must be running** on port 8000 (or set `PLAYWRIGHT_BASE_URL` environment variable)
2. **Frontend must be built** - The tests use the production build served by the backend

### Running Tests

```bash
# From the frontend directory
cd frontend

# Run all E2E tests (headless)
npm run test:e2e

# Run tests with UI mode (interactive)
npm run test:e2e:ui

# Run tests in headed mode (see browser)
npm run test:e2e:headed
```

### Test Configuration

Tests are configured in `frontend/playwright.config.ts`. The configuration:
- Automatically starts the backend server before tests (unless already running)
- Uses Chromium browser
- Has a 2-minute timeout for server startup
- Generates HTML reports

## Test Coverage

The smoke tests cover these critical flows:

1. **Homepage Load** - Verifies the app loads and shows the revision setup form
2. **Create Revision** - Tests creating a revision with basic information
3. **Answer Questions** - Tests displaying and answering questions
4. **View Summary** - Tests viewing the summary after completing questions
5. **File Upload UI** - Verifies file upload input is present
6. **Form Validation** - Tests HTML5 form validation
7. **Full Workflow** - End-to-end test of the complete revision workflow

## Writing New Tests

Add new test files in `frontend/e2e/` with the `.spec.ts` extension.

Example:

```typescript
import { test, expect } from '@playwright/test';

test('my new test', async ({ page }) => {
  await page.goto('/');
  // Your test code here
});
```

## CI/CD Integration

For Railway or other CI/CD platforms, you can run tests with:

```bash
cd frontend && npm run test:e2e
```

Set `CI=true` environment variable to:
- Disable test retries
- Use single worker
- Fail on `test.only()`

## Troubleshooting

### Tests fail with "Connection refused"
- Make sure the backend server is running on port 8000
- Or set `PLAYWRIGHT_BASE_URL` to your server URL

### Tests timeout
- Increase timeout in `playwright.config.ts`
- Check that the backend server starts correctly

### Tests pass locally but fail in CI
- Ensure all dependencies are installed
- Check that the backend server can start in CI environment
- Verify environment variables are set correctly

## Best Practices

1. **Keep tests fast** - Smoke tests should complete in under 2 minutes
2. **Test critical paths** - Focus on user-facing functionality
3. **Use data-testid** - Consider adding `data-testid` attributes to key elements for more reliable selectors
4. **Isolate tests** - Each test should be independent
5. **Clean up** - Tests should clean up after themselves (or use test isolation)

