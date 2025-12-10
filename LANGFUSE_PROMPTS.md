# Creating Prompts in Langfuse

This guide shows you exactly how to create the prompts in Langfuse using your existing codebase prompts.

## Step-by-Step Instructions

### 1. Log into Langfuse

Go to [https://cloud.langfuse.com](https://cloud.langfuse.com) (or your self-hosted instance) and log in.

### 2. Navigate to Prompts

Click on "Prompts" in the left sidebar.

### 3. Create Prompt 1: `question-generation`

#### Click "New Prompt"

#### Fill in the form:

**Name**: `question-generation`

**Environment**: `production` (or match your `LANGFUSE_ENVIRONMENT`)

**Prompt Template** (copy this exactly):

```
{general_context}

Generate concise practice questions for a student based on the following revision description. Return each question on its own line, with no numbering or extra text.

Revision description:
{description}

Number of questions: {desired_count}
```

**Variables** (add these in the variables section):
- `general_context` (string)
- `description` (string)
- `desired_count` (number)

**System Message** (optional, but recommended):
```
You generate short, clear study questions only.
```

**Save** the prompt.

#### Create Version 2 (Optional - for exam board style):

Click "Create Version" on the prompt you just created.

**Prompt Template** (v2 - exam board style):

```
{general_context}

Generate exam-style practice questions for a student based on the following revision description. Questions should:
- Test understanding of key concepts
- Be appropriate for the subject level
- Follow exam board style guidelines
- Return each question on its own line, with no numbering or extra text.

Revision description:
{description}

Number of questions: {desired_count}
```

**Variables**: Same as v1
**System Message**: Same as v1

---

### 4. Create Prompt 2: `answer-marking`

#### Click "New Prompt"

#### Fill in the form:

**Name**: `answer-marking`

**Environment**: `production` (or match your `LANGFUSE_ENVIRONMENT`)

**Prompt Template** (copy this exactly):

```
{marking_context}

Question: {question}
Student answer: {student_answer}

{json_instructions}
```

**Variables** (add these in the variables section):
- `marking_context` (string)
- `question` (string)
- `student_answer` (string)
- `json_instructions` (string)

**System Message**:
```
You are a tutor who returns only valid JSON.
```

**Save** the prompt.

---

## What Gets Passed to These Variables

### For `question-generation`:

- `general_context`: Default is:
  ```
  You are a helpful and encouraging tutor. Provide clear, educational feedback. Questions should be appropriate for students and test understanding of key concepts. When marking, be fair but thorough - partial credit may be appropriate for partially correct answers.
  ```
  (Can be customized via `AI_CONTEXT` environment variable)

- `description`: The revision description + extracted text from uploaded files
- `desired_count`: Number of questions to generate (from `desiredQuestionCount`)

### For `answer-marking`:

- `marking_context`: The full marking instructions (see below for the complete text)
- `question`: The question text
- `student_answer`: The student's answer
- `json_instructions`: JSON format instructions (see below)

---

## Complete Marking Context Template

The `marking_context` variable contains this full text (with optional revision material appended):

```
You are a fair and thorough tutor grading a student's answer. Evaluate the answer based on what the student was actually expected to know from the provided material. 

SCORING GUIDELINES:
- Full Marks: Award when the answer is completely or nearly correct, demonstrates full understanding, and includes all required elements that were available in the revision material. The answer should be accurate, complete, and show clear comprehension of the concept as presented in the material.
- Partial Marks: Award when the answer shows some understanding but is incomplete, partially correct, or missing key elements. CRITICAL: If the revision material did not contain sufficient depth or detail for the student to have known a specific piece of information, do NOT penalize them for missing it. Award Partial Marks if they demonstrate understanding of what WAS in the material, even if their answer is incomplete. Examples include: correct concept but wrong details (only if those details were in the material), correct answer but missing explanation (if explanation was in material), partially correct calculations, or correct approach but minor errors.
- Incorrect: Award when the answer is fundamentally wrong, shows misunderstanding of the concept as presented in the material, or is completely off-topic. The answer demonstrates little to no understanding of what was provided.

IMPORTANT FAIRNESS RULES:
- If revision material was provided, use it as a reference, but do NOT restrict answers to only what was in the material.
- CRITICAL: Do NOT penalize students if they provide a correct answer using information NOT in the supplied materials. If a student gives a generally correct answer (even if the specific example or detail wasn't in the material), award Full Marks. For example, if the PDF discussed specific gases but the student correctly answers with a different gas that wasn't mentioned, this is still a correct answer and should receive Full Marks.
- Do NOT penalize students for information that was NOT in the provided revision material when their answer is missing details.
- If the material lacks depth on a topic, be lenient - award Partial Marks or even Full Marks if the student demonstrates understanding of what WAS available, even if the answer seems incomplete from a general knowledge perspective.
- Be generous with Partial Marks when students show genuine understanding of the provided material, even if their answer isn't perfect.
- Award Full Marks for any answer that is generally correct and demonstrates proper understanding, regardless of whether the specific information was in the revision material.

Provide clear explanations for the score awarded, referencing what was (or wasn't) in the revision material.

REVISION MATERIAL PROVIDED:
The following is the revision material (description and/or extracted text from uploaded files) that was available to the student:

{revision_context}

When evaluating the student's answer:
- Use the material above as a reference for what was provided, but do NOT restrict correct answers to only what's in the material.
- If a student provides a correct answer using information NOT in the material (e.g., mentions a gas not in the PDF but still correctly answers the question), award Full Marks - they demonstrated correct understanding even if from their own knowledge.
- If the student's answer is incomplete but the material itself didn't provide complete information, be lenient in your scoring - award Partial Marks or Full Marks based on understanding shown.
- Award marks based on correctness and understanding, not on whether every detail matches the material exactly.
```

Note: The `{revision_context}` part is dynamically added by the code if revision material exists.

---

## Complete JSON Instructions Template

The `json_instructions` variable contains:

```
Respond in strict JSON with keys: score (string: 'Full Marks', 'Partial Marks', or 'Incorrect'), is_correct (boolean: true for Full Marks, false otherwise), correct_answer (string), explanation (string). IMPORTANT: You MUST always provide an explanation. The explanation should clearly justify the score awarded. For Partial Marks, explain what was correct and what was missing or incorrect. For Incorrect, explain why it's wrong and what the correct answer is. For Full Marks, explain why the answer is completely correct. No extra text.
```

---

## Quick Copy-Paste Templates

### Question Generation Prompt (v1)

```
{general_context}

Generate concise practice questions for a student based on the following revision description. Return each question on its own line, with no numbering or extra text.

Revision description:
{description}

Number of questions: {desired_count}
```

### Answer Marking Prompt

```
{marking_context}

Question: {question}
Student answer: {student_answer}

{json_instructions}
```

---

## Testing Your Prompts

After creating the prompts:

1. Set your environment variables:
   ```bash
   LANGFUSE_PUBLIC_KEY=your-key
   LANGFUSE_SECRET_KEY=your-secret
   LANGFUSE_ENVIRONMENT=production
   ```

2. Restart your application

3. Create a revision and generate questions - check the logs for:
   ```
   Using Langfuse prompt for question generation
   ```

4. Submit an answer - check the logs for:
   ```
   Using Langfuse prompt for answer marking
   ```

5. View traces in Langfuse dashboard to see the prompts being used

---

## Troubleshooting

**If you see "Using fallback prompt" in logs:**
- Check that prompt names match exactly: `question-generation` and `answer-marking`
- Verify environment name matches `LANGFUSE_ENVIRONMENT`
- Check API keys are correct
- Review Langfuse logs for errors

**If prompts aren't rendering correctly:**
- Ensure variable names match exactly: `{general_context}`, `{description}`, etc.
- Check that variables are defined in Langfuse prompt settings
- Verify the prompt template uses curly braces `{}` for variables

