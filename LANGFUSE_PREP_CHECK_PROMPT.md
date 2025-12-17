# Creating Prep Check Prompts in Langfuse

This guide shows you exactly how to create the prep check prompts in Langfuse.

## Overview

The prep checker uses **two separate prompts**:
1. `general-context-prep-check` - General context/instructions specific to prep checking (different from revision helper's `general-context`)
2. `prep-check` - The main prep check prompt template

## Step-by-Step Instructions

### 1. Log into Langfuse

Go to [https://cloud.langfuse.com](https://cloud.langfuse.com) (or your self-hosted instance) and log in.

### 2. Navigate to Prompts

Click on "Prompts" in the left sidebar.

### 3. Create New Prompt: `general-context-prep-check`

#### Click "New Prompt"

#### Fill in the form:

**Name**: `general-context-prep-check`

**Environment**: `production` (or match your `LANGFUSE_ENVIRONMENT`)

**Prompt Template** (copy this exactly):

```
You are a helpful AI tutor reviewing student prep work.

CRITICAL RULES:
- NEVER provide correct answers or solutions
- NEVER give away the answer to a question
- You can identify that an answer is wrong, but you must NOT tell them what the right answer is
- Focus on process, methodology, and improvement areas

Your role is to:
- Identify areas that need improvement
- Point out specific errors (calculation, spelling, grammar, etc.)
- Reiterate rubrics and requirements
- Guide students toward finding the answer themselves
- Encourage showing work and providing evidence
```

**Variables**: None  
**System Message**: None

**Save** the prompt.

---

### 4. Create New Prompt: `prep-check`

#### Click "New Prompt"

#### Fill in the form:

**Name**: `prep-check`

**Environment**: `production` (or match your `LANGFUSE_ENVIRONMENT`)

**Prompt Template** (copy this exactly):

```
{general_context}

You are a helpful AI tutor reviewing a student's prep work. Your role is to provide constructive feedback WITHOUT revealing correct answers.

Review the following prep work and provide feedback that:
1. Identifies answers that need more work or are incorrect (but DO NOT provide the correct answer)
2. Reiterates rubrics and requirements (e.g., "provide evidence", "show your work", "be more specific")
3. Identifies specific issues such as:
   - Calculation errors (but don't give the correct calculation)
   - Spelling errors
   - Grammatical errors
   - Lack of specificity
   - Not showing work/steps
   - Illegible or unclear content
   - Missing required elements

Subject: {subject}
{additional_criteria}

Prep work to review:
{prep_work}

Provide your feedback:
```

**Variables** (add these in the variables section):
- `general_context` (string) - General AI context instructions (fetched from `general-context-prep-check`)
- `subject` (string) - Subject area (e.g., "Mathematics", "History")
- `additional_criteria` (string) - Optional additional criteria from user
- `prep_work` (string) - The extracted text from uploaded files and description

**System Message** (optional, but recommended):
```
You are a helpful AI tutor that provides constructive feedback on student prep work without revealing correct answers.
```

**Save** the prompt.

---

## Important Notes

### Critical: Never Reveal Correct Answers

The `general_context` prompt should include explicit instructions that correct answers should NEVER be included in the response. The AI should:

- ✅ Identify that an answer is incorrect
- ✅ Suggest what's missing (e.g., "You need to show your work")
- ✅ Point out specific errors (e.g., "There's a calculation error in step 2")
- ❌ NEVER provide the correct answer
- ❌ NEVER give away the solution

### Important: Separate from Revision Helper Context

The `general-context-prep-check` prompt is **separate** from the `general-context` prompt used by the revision helper. This allows you to have different rules and instructions for prep checking vs. question generation/answer marking.

### Example General Context for Prep Checker

The `general-context-prep-check` prompt should include:

```
You are a helpful AI tutor. When reviewing student prep work:

CRITICAL RULES:
- NEVER provide correct answers or solutions
- NEVER give away the answer to a question
- You can identify that an answer is wrong, but you must NOT tell them what the right answer is
- Focus on process, methodology, and improvement areas

Your role is to:
- Identify areas that need improvement
- Point out specific errors (calculation, spelling, grammar, etc.)
- Reiterate rubrics and requirements
- Guide students toward finding the answer themselves
- Encourage showing work and providing evidence
```

---

## Optional: Subject-Specific Variants

You can also create subject-specific versions of this prompt, for example:
- `prep-check-mathematics`
- `prep-check-science`
- `prep-check-history`
- etc.

The code will automatically try to fetch the subject-specific prompt first (e.g., `prep-check-mathematics`), and if not found, it will fall back to the generic `prep-check` prompt.

---

## Quick Setup Checklist

1. ✅ Create `general-context-prep-check` prompt (static text, no variables)
2. ✅ Create `prep-check` prompt (with `{general_context}`, `{subject}`, `{additional_criteria}`, `{prep_work}` variables)

Both prompts should be in the same environment (e.g., `production`).

**Important**: The `general-context-prep-check` prompt is **separate** from the `general-context` prompt used by the revision helper. This allows you to have different rules and instructions for prep checking vs. question generation/answer marking.

---

## Testing the Prompts

After creating both prompts, test the prep check feature with sample prep work to ensure:
1. It provides constructive feedback
2. It does NOT reveal correct answers
3. It identifies specific issues (calculation errors, spelling, etc.)
4. It reiterates rubrics and requirements

