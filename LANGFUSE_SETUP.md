# Langfuse Integration Setup

This document describes how to set up and use Langfuse for prompt management and observability in the My Revision Helper application.

## Overview

Langfuse is integrated to provide:
- **Prompt Management**: Store and version prompts in Langfuse instead of hardcoding them
- **Observability**: Track all LLM calls with traces, generations, and metadata
- **Experiments**: Run A/B tests between prompt versions
- **Datasets**: Create datasets for regression testing

## Setup

### 1. Install Dependencies

The Langfuse SDK is already added to `requirements.txt`. Install it:

```bash
pip install -r requirements.txt
```

### 2. Get Langfuse Credentials

1. Sign up at [https://cloud.langfuse.com](https://cloud.langfuse.com) or deploy self-hosted
2. Create a new project
3. Go to Settings → API Keys
4. Create a new API key pair (Public Key and Secret Key)

### 3. Configure Environment Variables

Add these to your `.env` file:

```bash
# Langfuse Configuration
LANGFUSE_PUBLIC_KEY=your-public-key-here
LANGFUSE_SECRET_KEY=your-secret-key-here
LANGFUSE_HOST=https://cloud.langfuse.com  # Optional, defaults to cloud
LANGFUSE_ENVIRONMENT=production  # Optional, defaults to 'production'
```

For self-hosted Langfuse:

```bash
LANGFUSE_HOST=http://your-langfuse-instance:3000
```

### 4. Create Prompts in Langfuse

You need to create three prompts in Langfuse:

#### Prompt 1: `question-generation`

**Purpose**: Generate practice questions from revision material

**Template** (v1 - simple):
```
{general_context}

Generate concise practice questions for a student based on the following revision description. Return each question on its own line, with no numbering or extra text.

Revision description:
{description}

Number of questions: {desired_count}
```

**Template** (v2 - exam board style):
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

**Variables**:
- `general_context`: General AI context instructions
- `description`: Revision description and extracted text
- `desired_count`: Number of questions to generate

#### Prompt 2: `answer-marking`

**Purpose**: Mark student answers with three-tier scoring

**Template**:
```
{marking_context}

Question: {question}
Student answer: {student_answer}

{json_instructions}
```

**Variables**:
- `marking_context`: Detailed marking instructions with scoring guidelines
- `question`: The question text
- `student_answer`: The student's answer
- `json_instructions`: JSON format instructions

#### Prompt 3: `revision-summary` (optional, for future use)

**Purpose**: Generate summary of revision session

## Usage

### Automatic Prompt Fetching

The application automatically:
1. Tries to fetch prompts from Langfuse
2. Falls back to hardcoded prompts if Langfuse is unavailable
3. Logs which source is being used

### Tracing

All LLM calls are automatically traced with:
- **Trace name**: `question-generation` or `answer-marking`
- **Metadata**: user_id, revision_id, run_id, question_id, subject
- **Generations**: Model, input messages, output, tokens, latency

### Viewing Traces

1. Go to your Langfuse project dashboard
2. Navigate to "Traces" to see all LLM calls
3. Filter by trace name, user_id, or metadata
4. View detailed inputs/outputs for each generation

## Creating Datasets and Experiments

### 1. Create a Dataset

1. Go to Langfuse → Datasets
2. Create a new dataset (e.g., "Question Generation Test Cases")
3. Add items with:
   - Input variables (description, desired_count)
   - Expected output (sample questions)

### 2. Create an Experiment

1. Go to Langfuse → Experiments
2. Create experiment comparing:
   - `question-generation` v1 vs v2
   - `answer-marking` v1 vs v2
3. Run against your dataset
4. Use LLM-based evaluators to measure:
   - Quality, clarity, coverage (for questions)
   - Fairness, consistency (for marking)

### 3. Run Experiments

You can run experiments:
- Manually from Langfuse UI
- Via API in CI/CD pipeline
- Using the Langfuse Python SDK

## MCP Integration with Cursor

If you have Langfuse MCP server configured in Cursor:

1. Ask: "Fetch the current question-generation prompt from Langfuse and show it to me"
2. Ask: "Create a v3 variant that focuses more on spaced repetition"
3. The agent can interact with your prompts directly

## Environment-Specific Prompts

Use `LANGFUSE_ENVIRONMENT` to manage different prompt versions:
- `production`: Live prompts
- `staging`: Testing new prompts
- `development`: Experimental prompts

## Fallback Behavior

If Langfuse is unavailable:
- The app continues to work with hardcoded prompts
- All functionality remains intact
- Logs indicate when fallback is used

## Troubleshooting

### Prompts not found

- Check that prompts are created in Langfuse
- Verify environment name matches `LANGFUSE_ENVIRONMENT`
- Check API keys are correct
- Review logs for specific error messages

### Traces not appearing

- Verify API keys are set correctly
- Check network connectivity to Langfuse host
- Review application logs for errors
- Ensure Langfuse SDK is installed

### Performance concerns

- Prompt fetching is cached by Langfuse SDK
- Traces are sent asynchronously (non-blocking)
- Minimal performance impact

## Next Steps

1. Create the three prompts in Langfuse
2. Test with a few revisions
3. View traces in Langfuse dashboard
4. Create datasets for regression testing
5. Set up experiments for A/B testing prompt versions

