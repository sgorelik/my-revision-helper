#!/usr/bin/env python3
"""
Smoke test for Langfuse prompt integration.

Tests that all 5 prompts can be fetched from Langfuse and rendered correctly.
Run this after setting up prompts in Langfuse or after making changes to verify nothing broke.

Usage:
    python test_langfuse_prompts.py

Environment Variables Required:
    LANGFUSE_PUBLIC_KEY: Langfuse public key
    LANGFUSE_SECRET_KEY: Langfuse secret key
    LANGFUSE_HOST: Langfuse host (optional, defaults to https://cloud.langfuse.com)
    LANGFUSE_ENVIRONMENT: Environment name (optional, defaults to 'production')
"""

import sys
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from my_revision_helper.langfuse_client import (
    get_langfuse_client,
    fetch_prompt,
    render_prompt,
    get_langfuse_environment,
)


def test_langfuse_client():
    """Test that Langfuse client can be initialized."""
    print("=" * 70)
    print("TEST 1: Langfuse Client Initialization")
    print("=" * 70)
    
    client = get_langfuse_client()
    if client is None:
        print("✗ FAILED: Langfuse client not initialized")
        print("  → Check LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY environment variables")
        return False
    
    print("✓ PASSED: Langfuse client initialized successfully")
    env = get_langfuse_environment()
    print(f"  → Environment: {env}")
    return True


def test_general_context():
    """Test fetching and rendering general-context prompt."""
    print("\n" + "=" * 70)
    print("TEST 2: general-context Prompt")
    print("=" * 70)
    
    prompt_data = fetch_prompt("general-context")
    
    if not prompt_data:
        print("✗ FAILED: Could not fetch 'general-context' prompt from Langfuse")
        print("  → Create this prompt in Langfuse with name 'general-context'")
        return False
    
    prompt_text = prompt_data.get("prompt")
    if not prompt_text:
        print("✗ FAILED: Prompt data exists but 'prompt' field is empty")
        return False
    
    print("✓ PASSED: Successfully fetched 'general-context' prompt")
    print(f"  → Name: {prompt_data.get('name')}")
    print(f"  → Version: {prompt_data.get('version')}")
    print(f"  → Environment: {prompt_data.get('environment')}")
    print(f"  → Length: {len(prompt_text)} characters")
    print(f"  → Preview: {prompt_text[:100]}...")
    
    # This prompt has no variables, so no rendering test needed
    return True


def test_marking_context():
    """Test fetching and rendering marking-context prompt."""
    print("\n" + "=" * 70)
    print("TEST 3: marking-context Prompt")
    print("=" * 70)
    
    prompt_data = fetch_prompt("marking-context")
    
    if not prompt_data:
        print("✗ FAILED: Could not fetch 'marking-context' prompt from Langfuse")
        print("  → Create this prompt in Langfuse with name 'marking-context'")
        return False
    
    prompt_text = prompt_data.get("prompt")
    if not prompt_text:
        print("✗ FAILED: Prompt data exists but 'prompt' field is empty")
        return False
    
    print("✓ PASSED: Successfully fetched 'marking-context' prompt")
    print(f"  → Name: {prompt_data.get('name')}")
    print(f"  → Version: {prompt_data.get('version')}")
    print(f"  → Environment: {prompt_data.get('environment')}")
    print(f"  → Length: {len(prompt_text)} characters")
    print(f"  → Preview: {prompt_text[:100]}...")
    
    # This prompt has no variables, so no rendering test needed
    return True


def test_revision_context_template():
    """Test fetching and rendering revision-context-template prompt."""
    print("\n" + "=" * 70)
    print("TEST 4: revision-context-template Prompt")
    print("=" * 70)
    
    prompt_data = fetch_prompt("revision-context-template")
    
    if not prompt_data:
        print("✗ FAILED: Could not fetch 'revision-context-template' prompt from Langfuse")
        print("  → Create this prompt in Langfuse with name 'revision-context-template'")
        return False
    
    prompt_template = prompt_data.get("prompt")
    if not prompt_template:
        print("✗ FAILED: Prompt data exists but 'prompt' field is empty")
        return False
    
    print("✓ PASSED: Successfully fetched 'revision-context-template' prompt")
    print(f"  → Name: {prompt_data.get('name')}")
    print(f"  → Version: {prompt_data.get('version')}")
    print(f"  → Environment: {prompt_data.get('environment')}")
    print(f"  → Length: {len(prompt_template)} characters")
    
    # Test rendering with sample revision_context
    try:
        sample_revision = "Sample revision material: This is a test of the revision context template."
        rendered = render_prompt(
            prompt_template,
            {"revision_context": sample_revision}
        )
        print("✓ PASSED: Successfully rendered template with sample revision_context")
        print(f"  → Rendered length: {len(rendered)} characters")
        print(f"  → Contains revision: {'revision_context' in rendered or sample_revision in rendered}")
    except KeyError as e:
        print(f"✗ FAILED: Template missing required variable: {e}")
        return False
    except Exception as e:
        print(f"✗ FAILED: Error rendering template: {e}")
        return False
    
    return True


def test_question_generation():
    """Test fetching and rendering question-generation prompt."""
    print("\n" + "=" * 70)
    print("TEST 5: question-generation Prompt")
    print("=" * 70)
    
    prompt_data = fetch_prompt("question-generation")
    
    if not prompt_data:
        print("✗ FAILED: Could not fetch 'question-generation' prompt from Langfuse")
        print("  → Create this prompt in Langfuse with name 'question-generation'")
        return False
    
    prompt_template = prompt_data.get("prompt")
    if not prompt_template:
        print("✗ FAILED: Prompt data exists but 'prompt' field is empty")
        return False
    
    print("✓ PASSED: Successfully fetched 'question-generation' prompt")
    print(f"  → Name: {prompt_data.get('name')}")
    print(f"  → Version: {prompt_data.get('version')}")
    print(f"  → Environment: {prompt_data.get('environment')}")
    print(f"  → Length: {len(prompt_template)} characters")
    
    # Test rendering with sample variables
    try:
        # Get general_context from Langfuse for realistic test
        general_context_data = fetch_prompt("general-context")
        general_context = general_context_data.get("prompt") if general_context_data else "Test general context"
        
        sample_vars = {
            "general_context": general_context,
            "description": "Test revision description about photosynthesis and plant biology.",
            "desired_count": 3,
        }
        
        rendered = render_prompt(prompt_template, sample_vars)
        print("✓ PASSED: Successfully rendered template with sample variables")
        print(f"  → Rendered length: {len(rendered)} characters")
        print(f"  → Contains description: {'description' in rendered.lower() or 'photosynthesis' in rendered.lower()}")
        print(f"  → Contains count: {'3' in rendered or 'desired_count' in rendered.lower()}")
    except KeyError as e:
        print(f"✗ FAILED: Template missing required variable: {e}")
        print(f"  → Template expects variables: {_extract_variables(prompt_template)}")
        return False
    except Exception as e:
        print(f"✗ FAILED: Error rendering template: {e}")
        return False
    
    return True


def test_answer_marking():
    """Test fetching and rendering answer-marking prompt."""
    print("\n" + "=" * 70)
    print("TEST 6: answer-marking Prompt")
    print("=" * 70)
    
    prompt_data = fetch_prompt("answer-marking")
    
    if not prompt_data:
        print("✗ FAILED: Could not fetch 'answer-marking' prompt from Langfuse")
        print("  → Create this prompt in Langfuse with name 'answer-marking'")
        return False
    
    prompt_template = prompt_data.get("prompt")
    if not prompt_template:
        print("✗ FAILED: Prompt data exists but 'prompt' field is empty")
        return False
    
    print("✓ PASSED: Successfully fetched 'answer-marking' prompt")
    print(f"  → Name: {prompt_data.get('name')}")
    print(f"  → Version: {prompt_data.get('version')}")
    print(f"  → Environment: {prompt_data.get('environment')}")
    print(f"  → Length: {len(prompt_template)} characters")
    
    # Test rendering with sample variables
    try:
        # Get dependencies from Langfuse for realistic test
        general_context_data = fetch_prompt("general-context")
        general_context = general_context_data.get("prompt") if general_context_data else "Test general context"
        
        marking_context_data = fetch_prompt("marking-context")
        marking_context = marking_context_data.get("prompt") if marking_context_data else "Test marking context"
        
        # Test with revision context template
        revision_template_data = fetch_prompt("revision-context-template")
        if revision_template_data:
            revision_template = revision_template_data.get("prompt")
            sample_revision = "Sample revision material about photosynthesis."
            marking_context += "\n\n" + render_prompt(
                revision_template,
                {"revision_context": sample_revision}
            )
        
        json_instructions = (
            "Respond in strict JSON with keys: score (string: 'Full Marks', 'Partial Marks', or 'Incorrect'), "
            "is_correct (boolean: true for Full Marks, false otherwise), correct_answer (string), "
            "explanation (string). IMPORTANT: You MUST always provide an explanation."
        )
        
        sample_vars = {
            "general_context": general_context,
            "marking_context": marking_context,
            "question": "What is photosynthesis?",
            "student_answer": "Photosynthesis is the process by which plants convert sunlight into energy.",
            "json_instructions": json_instructions,
        }
        
        rendered = render_prompt(prompt_template, sample_vars)
        print("✓ PASSED: Successfully rendered template with sample variables")
        print(f"  → Rendered length: {len(rendered)} characters")
        print(f"  → Contains question: {'question' in rendered.lower() or 'photosynthesis' in rendered.lower()}")
        print(f"  → Contains student_answer: {'student' in rendered.lower() or 'answer' in rendered.lower()}")
        print(f"  → Contains json_instructions: {'json' in rendered.lower()}")
    except KeyError as e:
        print(f"✗ FAILED: Template missing required variable: {e}")
        print(f"  → Template expects variables: {_extract_variables(prompt_template)}")
        return False
    except Exception as e:
        print(f"✗ FAILED: Error rendering template: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


def test_question_generation_multiple_choice():
    """Test fetching and rendering question-generation-multiple-choice prompt."""
    print("\n" + "=" * 70)
    print("TEST 7: question-generation-multiple-choice Prompt")
    print("=" * 70)
    
    prompt_data = fetch_prompt("question-generation-multiple-choice")
    
    if not prompt_data:
        print("✗ FAILED: Could not fetch 'question-generation-multiple-choice' prompt from Langfuse")
        print("  → Create this prompt in Langfuse with name 'question-generation-multiple-choice'")
        print("  → See LANGFUSE_MULTIPLE_CHOICE_PROMPT.md for details")
        return False
    
    prompt_template = prompt_data.get("prompt")
    if not prompt_template:
        print("✗ FAILED: Prompt data exists but 'prompt' field is empty")
        return False
    
    print("✓ PASSED: Successfully fetched 'question-generation-multiple-choice' prompt")
    print(f"  → Name: {prompt_data.get('name')}")
    print(f"  → Version: {prompt_data.get('version')}")
    print(f"  → Environment: {prompt_data.get('environment')}")
    print(f"  → Length: {len(prompt_template)} characters")
    
    # Test rendering with sample variables
    try:
        # Get general_context from Langfuse for realistic test
        general_context_data = fetch_prompt("general-context")
        general_context = general_context_data.get("prompt") if general_context_data else "Test general context"
        
        sample_vars = {
            "general_context": general_context,
            "description": "Test revision description about photosynthesis and plant biology.",
            "desired_count": 3,
        }
        
        rendered = render_prompt(prompt_template, sample_vars)
        print("✓ PASSED: Successfully rendered template with sample variables")
        print(f"  → Rendered length: {len(rendered)} characters")
        print(f"  → Contains description: {'description' in rendered.lower() or 'photosynthesis' in rendered.lower()}")
        print(f"  → Contains count: {'3' in rendered or 'desired_count' in rendered.lower()}")
        print(f"  → Contains format instructions: {'question:' in rendered.lower() or 'correct:' in rendered.lower()}")
    except KeyError as e:
        print(f"✗ FAILED: Template missing required variable: {e}")
        print(f"  → Template expects variables: {_extract_variables(prompt_template)}")
        return False
    except Exception as e:
        print(f"✗ FAILED: Error rendering template: {e}")
        return False
    
    return True


def test_subject_specific_fallback():
    """Test subject-specific prompt fallback logic."""
    print("\n" + "=" * 70)
    print("TEST 7: Subject-Specific Prompt Fallback")
    print("=" * 70)
    
    # Test question-generation with subject
    prompt_data = fetch_prompt("question-generation", subject="Mathematics")
    
    if prompt_data:
        prompt_name = prompt_data.get("name")
        if "mathematics" in prompt_name.lower():
            print("✓ PASSED: Found subject-specific prompt for Mathematics")
            print(f"  → Prompt name: {prompt_name}")
        else:
            print("ℹ INFO: Subject-specific prompt not found, using base prompt (this is OK)")
            print(f"  → Prompt name: {prompt_name}")
    else:
        print("ℹ INFO: No prompt found (this is OK if base prompt exists)")
    
    # Test answer-marking with subject
    prompt_data = fetch_prompt("answer-marking", subject="Computer Science")
    
    if prompt_data:
        prompt_name = prompt_data.get("name")
        if "computer" in prompt_name.lower() or "science" in prompt_name.lower():
            print("✓ PASSED: Found subject-specific prompt for Computer Science")
            print(f"  → Prompt name: {prompt_name}")
        else:
            print("ℹ INFO: Subject-specific prompt not found, using base prompt (this is OK)")
            print(f"  → Prompt name: {prompt_name}")
    else:
        print("ℹ INFO: No prompt found (this is OK if base prompt exists)")
    
    return True


def _extract_variables(template: str) -> list:
    """Extract variable names from a template string."""
    import re
    # Find all {variable_name} patterns
    variables = re.findall(r'\{(\w+)\}', template)
    return list(set(variables))  # Return unique variables


def run_all_tests():
    """Run all tests and report results."""
    print("\n" + "=" * 70)
    print("LANGFUSE PROMPT SMOKE TEST")
    print("=" * 70)
    print("\nThis test verifies that all prompts are correctly set up in Langfuse.")
    print("Run this after creating/updating prompts to ensure nothing broke.\n")
    
    results = []
    
    # Test 1: Client initialization
    results.append(("Langfuse Client", test_langfuse_client()))
    
    # Only continue if client is available
    if not results[0][1]:
        print("\n" + "=" * 70)
        print("SUMMARY: Cannot proceed without Langfuse client")
        print("=" * 70)
        print("✗ Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY environment variables")
        return False
    
    # Test 2-6: Core prompts
    results.append(("general-context", test_general_context()))
    results.append(("marking-context", test_marking_context()))
    results.append(("revision-context-template", test_revision_context_template()))
    results.append(("question-generation", test_question_generation()))
    results.append(("answer-marking", test_answer_marking()))
    results.append(("question-generation-multiple-choice", test_question_generation_multiple_choice()))
    
    # Test 8: Subject-specific fallback (informational)
    results.append(("Subject-Specific Fallback", test_subject_specific_fallback()))
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Your Langfuse prompts are correctly configured.")
        return True
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Check the output above for details.")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

