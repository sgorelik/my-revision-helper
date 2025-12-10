# Subject-Specific Prompts in Langfuse

This guide explains how to create and use subject-specific prompts for both question generation and answer marking.

## How It Works

The code automatically tries to fetch subject-specific prompts first, then falls back to the generic prompt:

**For Question Generation:**
1. **First attempt**: `question-generation-{subject}` (e.g., `question-generation-mathematics`)
2. **Fallback**: `question-generation` (generic prompt)

**For Answer Marking:**
1. **First attempt**: `answer-marking-{subject}` (e.g., `answer-marking-mathematics`)
2. **Fallback**: `answer-marking` (generic prompt)

## Creating Subject-Specific Prompts

### Option 1: Create Separate Prompts per Subject (Recommended)

**For Question Generation**, create prompts with names like:
- `question-generation-mathematics`
- `question-generation-science`
- `question-generation-english`
- `question-generation-history`
- etc.

**For Answer Marking**, create prompts with names like:
- `answer-marking-mathematics`
- `answer-marking-science`
- `answer-marking-english`
- `answer-marking-history`
- etc.

**Steps:**

1. Go to Langfuse → Prompts → New Prompt
2. **Name**: `question-generation-mathematics` (or your subject)
3. **Environment**: `production` (or your environment)
4. **Prompt Template**: Customize for that subject

**Example for Mathematics:**

```
{general_context}

Generate concise mathematics practice questions for a student based on the following revision description. Questions should:
- Focus on problem-solving and calculations
- Test understanding of mathematical concepts and formulas
- Include numerical problems where appropriate
- Return each question on its own line, with no numbering or extra text.

Revision description:
{description}

Number of questions: {desired_count}
```

**Example for Science:**

```
{general_context}

Generate concise science practice questions for a student based on the following revision description. Questions should:
- Test understanding of scientific concepts and principles
- Include questions about processes, mechanisms, and relationships
- Cover both theoretical understanding and practical applications
- Return each question on its own line, with no numbering or extra text.

Revision description:
{description}

Number of questions: {desired_count}
```

**Variables**: Same as generic prompt:
- `general_context`
- `description`
- `desired_count`

**System Message**: Same as generic prompt:
```
You generate short, clear study questions only.
```

### Answer Marking Subject-Specific Prompts

**Example for Mathematics:**

```
{marking_context}

Question: {question}
Student answer: {student_answer}

{json_instructions}
```

**Note**: For mathematics, you might want to customize the `marking_context` variable to emphasize:
- Checking mathematical reasoning and steps
- Verifying calculations
- Awarding partial credit for correct methods even with calculation errors
- Recognizing multiple valid approaches

**Example for Science:**

```
{marking_context}

Question: {question}
Student answer: {student_answer}

{json_instructions}
```

**Note**: For science, you might want to customize the `marking_context` variable to emphasize:
- Understanding of scientific concepts and principles
- Correct use of scientific terminology
- Recognition of cause-and-effect relationships
- Application of scientific methods

### Option 2: Use Prompt Versions

You can also use versions within the same prompt name:
- `question-generation` v1: Generic
- `question-generation` v2: Mathematics-focused
- `question-generation` v3: Science-focused

Then use the `version` parameter in code (requires code changes).

## Subject Name Normalization

The code automatically normalizes subject names:
- "Mathematics" → `mathematics`
- "Computer Science" → `computer-science`
- "Physical Education" → `physical-education`

So create prompts using lowercase with hyphens:
- ✅ `question-generation-mathematics`
- ✅ `question-generation-computer-science`
- ❌ `question-generation-Mathematics` (won't match)

## Current Subject List

Based on your codebase, these subjects are supported:
- Mathematics
- Science
- English
- History
- Geography
- Art
- Music
- Physical Education
- Computer Science
- Foreign Languages
- Other

## Code Locations

The subject-specific prompt fetching happens in two places:

### Question Generation

**File**: `my_revision_helper/api.py`
**Function**: `start_run()` 
**Line**: ~720

```python
# Get subject for subject-specific prompts
subject = revision.get("subject") if revision else None

# Try to fetch prompt from Langfuse
langfuse_prompt_data = fetch_prompt("question-generation", subject=subject)
```

### Answer Marking

**File**: `my_revision_helper/api.py`
**Function**: `submit_answer()`
**Line**: ~1025

```python
# Get subject for subject-specific prompts and JSON instructions
subject = None
if revision:
    subject = revision.get("subject")

# Try to fetch prompt from Langfuse
langfuse_prompt_data = fetch_prompt("answer-marking", subject=subject)
```

The `fetch_prompt()` function in `langfuse_client.py` handles the fallback logic automatically for both.

## Testing

### Testing Question Generation

1. Create a subject-specific prompt in Langfuse (e.g., `question-generation-mathematics`)
2. Create a revision with subject "Mathematics"
3. Generate questions
4. Check logs for:
   ```
   Trying subject-specific prompt: 'question-generation-mathematics' for subject 'Mathematics'
   Fetched prompt 'question-generation-mathematics' from Langfuse
   ```

If the subject-specific prompt doesn't exist, you'll see:
```
Trying subject-specific prompt: 'question-generation-mathematics' for subject 'Mathematics'
Subject-specific prompt 'question-generation-mathematics' not found, trying base prompt 'question-generation'
Fetched base prompt 'question-generation' from Langfuse
```

### Testing Answer Marking

1. Create a subject-specific prompt in Langfuse (e.g., `answer-marking-mathematics`)
2. Create a revision with subject "Mathematics"
3. Submit an answer to a question
4. Check logs for:
   ```
   Trying subject-specific prompt: 'answer-marking-mathematics' for subject 'Mathematics'
   Fetched prompt 'answer-marking-mathematics' from Langfuse
   Using Langfuse prompt for answer marking
   ```

If the subject-specific prompt doesn't exist, you'll see:
```
Trying subject-specific prompt: 'answer-marking-mathematics' for subject 'Mathematics'
Subject-specific prompt 'answer-marking-mathematics' not found, trying base prompt 'answer-marking'
Fetched base prompt 'answer-marking' from Langfuse
Using Langfuse prompt for answer marking
```

## Best Practices

1. **Start with generic prompts**: Create `question-generation` and `answer-marking` first, test they work
2. **Add subject-specific as needed**: Only create subject-specific prompts for subjects that need different approaches
3. **Keep variables consistent**: Use the same variable names across all prompts
4. **Document differences**: Note in Langfuse prompt description what makes each subject-specific version different
5. **Customize marking context**: For answer marking, you can customize the `marking_context` variable to be subject-specific

## Example: Mathematics vs Science

### Question Generation

**Mathematics prompt** might emphasize:
- Problem-solving steps
- Numerical calculations
- Formula application
- Step-by-step reasoning

**Science prompt** might emphasize:
- Scientific concepts and principles
- Cause-and-effect relationships
- Process understanding
- Real-world applications

### Answer Marking

**Mathematics marking** might emphasize:
- Checking mathematical reasoning and methodology
- Verifying calculations step-by-step
- Awarding partial credit for correct methods even with calculation errors
- Recognizing multiple valid solution approaches
- Being lenient with minor arithmetic errors if the method is correct

**Science marking** might emphasize:
- Understanding of scientific concepts and principles
- Correct use of scientific terminology
- Recognition of cause-and-effect relationships
- Application of scientific methods
- Understanding of processes and mechanisms

Both use the same variables, but the instructions differ to match the subject's nature.

