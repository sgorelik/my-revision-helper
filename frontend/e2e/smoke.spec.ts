import { test, expect } from '@playwright/test';

/**
 * Smoke tests for critical user flows.
 * These tests ensure basic functionality works after UI changes.
 */

test.describe('Revision Helper - Smoke Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the app
    await page.goto('/');
    // Wait for the page to load
    await page.waitForLoadState('networkidle');
  });

  test('should load the homepage and display the revision setup form', async ({ page }) => {
    // Check that the main heading is visible
    await expect(page.getByRole('heading', { name: /My Revision Helper/i })).toBeVisible();
    
    // Check that the setup form is visible
    await expect(page.getByRole('heading', { name: /Set Up a Revision/i })).toBeVisible();
    
    // Check that key form fields are present
    await expect(page.getByLabel(/Revision Name/i)).toBeVisible();
    await expect(page.getByLabel(/Subject/i)).toBeVisible();
    await expect(page.getByLabel(/Topic Areas/i)).toBeVisible();
    await expect(page.getByLabel(/Description/i)).toBeVisible();
  });

  test('should create a revision with basic information', async ({ page }) => {
    // Fill in the revision form
    await page.getByLabel(/Revision Name/i).fill('Smoke Test Revision');
    await page.getByLabel(/Subject/i).fill('Mathematics');
    await page.getByLabel(/Topic Areas/i).fill('Algebra, Geometry');
    await page.getByLabel(/Description/i).fill('Test revision for smoke testing');
    
    // Set question count and accuracy threshold
    await page.getByLabel(/Desired Number of Questions/i).fill('2');
    await page.getByLabel(/Accuracy Threshold/i).fill('80');
    
    // Submit the form
    await page.getByRole('button', { name: /Create Revision/i }).click();
    
    // Wait for the revision to be created and the run to start
    // The page should transition to the "Run Revision" view
    await expect(page.getByRole('heading', { name: /Run Revision/i })).toBeVisible({ timeout: 10000 });
    
    // Verify we can see the revision name
    await expect(page.getByText(/Smoke Test Revision/i)).toBeVisible();
  });

  test('should display and answer a question', async ({ page }) => {
    // First create a revision
    await page.getByLabel(/Revision Name/i).fill('Question Test');
    await page.getByLabel(/Subject/i).fill('Test Subject');
    await page.getByLabel(/Desired Number of Questions/i).fill('1');
    await page.getByLabel(/Accuracy Threshold/i).fill('80');
    
    await page.getByRole('button', { name: /Create Revision/i }).click();
    
    // Wait for the question to appear
    await expect(page.getByRole('heading', { name: /Question/i })).toBeVisible({ timeout: 10000 });
    
    // Verify question text is displayed
    const questionText = await page.locator('text=/Question/').locator('..').locator('p').first();
    await expect(questionText).toBeVisible();
    
    // Enter an answer
    await page.getByLabel(/Your Answer/i).fill('Test answer');
    
    // Submit the answer
    await page.getByRole('button', { name: /Submit Answer/i }).click();
    
    // Wait for the result to appear - use heading role to find the result status
    const resultHeading = page.getByRole('heading', { name: /^(Correct!|Incorrect)$/i });
    await expect(resultHeading).toBeVisible({ timeout: 10000 });
    
    // Verify we can see the correct answer
    await expect(page.getByText(/Correct answer:/i)).toBeVisible();
    
    // If the answer is incorrect, verify explanation is shown
    const isIncorrect = await resultHeading.textContent().then(text => text?.toLowerCase().includes('incorrect'));
    if (isIncorrect) {
      await expect(page.getByText(/Explanation:/i)).toBeVisible();
    }
  });

  // TODO: Fix and enable summary test once summary workflow is finalized
  // test('should display summary after completing questions', async ({ page }) => {
  //   // Create a revision with 1 question
  //   // Answer the question
  //   // Navigate to summary
  //   // Verify summary displays correctly
  // });

  test('should handle file upload UI', async ({ page }) => {
    // Check that file upload input is present
    const fileInput = page.locator('input[type="file"]');
    await expect(fileInput).toBeVisible();
    
    // Verify the file input accepts images
    const acceptAttr = await fileInput.getAttribute('accept');
    expect(acceptAttr).toContain('image');
  });

  test('should display error messages for validation', async ({ page }) => {
    // Try to submit form without required fields
    await page.getByRole('button', { name: /Create Revision/i }).click();
    
    // HTML5 validation should prevent submission
    // Check that the form doesn't submit (revision name field should still be visible)
    await expect(page.getByLabel(/Revision Name/i)).toBeVisible();
  });

  test('should navigate through revision workflow', async ({ page }) => {
    // Step 1: Create revision
    await page.getByLabel(/Revision Name/i).fill('Workflow Test');
    await page.getByLabel(/Subject/i).fill('Test');
    await page.getByLabel(/Desired Number of Questions/i).fill('1');
    await page.getByLabel(/Accuracy Threshold/i).fill('80');
    await page.getByRole('button', { name: /Create Revision/i }).click();
    
    // Step 2: Verify we're in the run view
    await expect(page.getByRole('heading', { name: /Run Revision/i })).toBeVisible({ timeout: 10000 });
    
    // Step 3: Answer question
    await expect(page.getByRole('heading', { name: /Question/i })).toBeVisible({ timeout: 10000 });
    await page.getByLabel(/Your Answer/i).fill('Answer');
    await page.getByRole('button', { name: /Submit Answer/i }).click();
    
    // Step 4: View result - use heading role to find the result status
    await expect(page.getByRole('heading', { name: /^(Correct!|Incorrect)$/i })).toBeVisible({ timeout: 10000 });
    
    // Step 5: View summary
    const viewSummaryButton = page.getByRole('button', { name: /View Summary/i });
    if (await viewSummaryButton.isVisible()) {
      await viewSummaryButton.click();
      await expect(page.getByRole('heading', { name: /Summary/i })).toBeVisible({ timeout: 10000 });
    }
  });
});

