# Langfuse Multiple Choice Question Generation Prompt

This document describes the prompt that needs to be added to Langfuse for multiple choice question generation.

## Prompt Name

**Name**: `question-generation-multiple-choice`  
**Environment**: `production` (or your `LANGFUSE_ENVIRONMENT`)

## Prompt Template

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

## Variables

Add these variables in the Langfuse prompt configuration:

- `general_context` (string) - General AI context/instructions (fetched from `general-context` prompt)
- `description` (string) - The revision description + extracted text from uploaded files
- `desired_count` (number) - Number of questions to generate

## System Message

```
You generate short, clear study questions only.
```

## Subject-Specific Variants

You can also create subject-specific versions of this prompt:

- `question-generation-multiple-choice-mathematics`
- `question-generation-multiple-choice-science`
- `question-generation-multiple-choice-english`
- etc.

The code will automatically try subject-specific prompts first, then fall back to the generic `question-generation-multiple-choice` prompt.

## Example Subject-Specific Prompt (Mathematics)

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

## How It Works

1. When a revision is created with `questionStyle: "multiple-choice"`, the code will:
   - First try to fetch a subject-specific prompt (e.g., `question-generation-multiple-choice-mathematics`)
   - If not found, try the generic `question-generation-multiple-choice` prompt
   - If still not found, fall back to hardcoded prompt

2. The prompt is rendered with:
   - `general_context`: Fetched from `general-context` prompt (or fallback)
   - `description`: The revision description + extracted text from uploaded files
   - `desired_count`: Number of questions to generate

3. The response is parsed by `parse_multiple_choice_questions()` function to extract:
   - Question text
   - Four options (A, B, C, D)
   - Correct answer index
   - Rationale/explanation

## Quick Setup Checklist

1. ✅ Create `question-generation-multiple-choice` prompt in Langfuse
2. ✅ Add variables: `general_context`, `description`, `desired_count`
3. ✅ Set system message: "You generate short, clear study questions only."
4. ✅ (Optional) Create subject-specific variants for better customization

## Testing

After creating the prompt in Langfuse, you can test it using:

```bash
python test_langfuse_prompts.py
```

Or run the smoke test to verify all prompts are correctly set up.

