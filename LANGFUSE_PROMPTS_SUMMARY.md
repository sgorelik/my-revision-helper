# Langfuse Prompts Summary

This document lists all prompts that need to be configured in Langfuse for the application to work properly.

## Required Prompts (6 total)

### 1. `general-context`
**Purpose**: General AI context/instructions used across all AI interactions  
**Variables**: None (static text)  
**Status**: ✅ Already configured (from previous setup)

### 2. `marking-context`
**Purpose**: Base marking instructions for evaluating student answers  
**Variables**: None (static text)  
**Status**: ✅ Already configured (from previous setup)

### 3. `revision-context-template`
**Purpose**: Template for including revision material context in marking  
**Variables**: `revision_context` (string)  
**Status**: ✅ Already configured (from previous setup)

### 4. `question-generation`
**Purpose**: Generate free-text practice questions  
**Variables**: `general_context`, `description`, `desired_count`  
**Status**: ✅ Already configured (from previous setup)

### 5. `answer-marking`
**Purpose**: Evaluate and mark student answers (free-text questions)  
**Variables**: `general_context`, `marking_context`, `question`, `student_answer`, `json_instructions`  
**Status**: ✅ Already configured (from previous setup)

### 6. `question-generation-multiple-choice` ⭐ NEW
**Purpose**: Generate multiple choice questions with options, correct answer, and rationale  
**Variables**: `general_context`, `description`, `desired_count`  
**Status**: Created

---

## New Prompt: `question-generation-multiple-choice`

### Quick Setup

1. **Go to Langfuse → Prompts → New Prompt**

2. **Fill in the form:**
   - **Name**: `question-generation-multiple-choice`
   - **Environment**: `production` (or match your `LANGFUSE_ENVIRONMENT`)

3. **Prompt Template** (copy exactly):
```
{general_context}

Generate multiple choice practice questions for a student based on the following revision description. For each question, provide:
1. The question text
2. Four answer options (A, B, C, D)
3. The correct answer (A, B, C, or D)
4. A brief explanation/rationale for why the correct answer is correct

Format each question as:
QUESTION: [question text]
A) [option A]
B) [option B]
C) [option C]
D) [option D]
CORRECT: [A/B/C/D]
RATIONALE: [explanation of why the correct answer is correct]

Revision description:
{description}

Number of questions: {desired_count}
```

4. **Variables** (add these in the variables section):
   - `general_context` (string)
   - `description` (string)
   - `desired_count` (number)

5. **System Message**:
```
You generate short, clear study questions only.
```

6. **Save** the prompt

---

## Optional: Subject-Specific Variants

You can create subject-specific versions for better customization:

- `question-generation-multiple-choice-mathematics`
- `question-generation-multiple-choice-science`
- `question-generation-multiple-choice-english`
- etc.

The code will automatically try subject-specific prompts first, then fall back to the generic `question-generation-multiple-choice` prompt.

### Example Subject-Specific Prompt (Mathematics)

**Name**: `question-generation-multiple-choice-mathematics`  
**Environment**: `production`

**Prompt Template**:
```
{general_context}

Generate multiple choice mathematics practice questions for a student based on the following revision description. Questions should:
- Focus on problem-solving and calculations
- Test understanding of mathematical concepts and formulas
- Include numerical problems where appropriate
- For each question, provide:
  1. The question text
  2. Four answer options (A, B, C, D)
  3. The correct answer (A, B, C, or D)
  4. A brief explanation/rationale for why the correct answer is correct

Format each question as:
QUESTION: [question text]
A) [option A]
B) [option B]
C) [option C]
D) [option D]
CORRECT: [A/B/C/D]
RATIONALE: [explanation of why the correct answer is correct]

Revision description:
{description}

Number of questions: {desired_count}
```

**Variables**: Same as generic prompt  
**System Message**: Same as generic prompt

---

## Testing

After creating the prompt, run the smoke test:

```bash
python test_langfuse_prompts.py
```

This will verify that all prompts (including the new multiple choice prompt) are correctly configured.

---

## How It Works

1. **When a revision is created with `questionStyle: "multiple-choice"`**:
   - Code first tries: `question-generation-multiple-choice-{subject}` (e.g., `question-generation-multiple-choice-mathematics`)
   - If not found, tries: `question-generation-multiple-choice` (generic)
   - If still not found, falls back to hardcoded prompt

2. **The prompt is rendered with**:
   - `general_context`: Fetched from `general-context` prompt
   - `description`: Revision description + extracted text from uploaded files
   - `desired_count`: Number of questions to generate

3. **The response is parsed** by `parse_multiple_choice_questions()` to extract:
   - Question text
   - Four options (A, B, C, D)
   - Correct answer index
   - Rationale/explanation

---

## Files Updated

- ✅ `my_revision_helper/api.py` - Updated to fetch multiple choice prompt from Langfuse
- ✅ `test_langfuse_prompts.py` - Added test for multiple choice prompt
- ✅ `LANGFUSE_MULTIPLE_CHOICE_PROMPT.md` - Detailed documentation
- ✅ `LANGFUSE_PROMPTS_SUMMARY.md` - This file

---

## Next Steps

1. Create the `question-generation-multiple-choice` prompt in Langfuse using the template above
2. (Optional) Create subject-specific variants for better customization
3. Run `python test_langfuse_prompts.py` to verify the setup
4. Test creating a revision with `questionStyle: "multiple-choice"` in the app

