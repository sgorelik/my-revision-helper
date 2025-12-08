"""
Langfuse integration for prompt management and observability.

This module provides:
- Langfuse client initialization
- Prompt fetching from Langfuse
- Tracing for OpenAI calls
- Metadata logging (user_id, revision_id, question_id, etc.)

Environment Variables:
    LANGFUSE_PUBLIC_KEY: Langfuse public key (required)
    LANGFUSE_SECRET_KEY: Langfuse secret key (required)
    LANGFUSE_HOST: Langfuse host URL (optional, defaults to https://cloud.langfuse.com)
    LANGFUSE_ENVIRONMENT: Environment name for prompts (optional, defaults to 'production')
"""

from __future__ import annotations

import os
import logging
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Try to import Langfuse
try:
    from langfuse import Langfuse
    LANGFUSE_AVAILABLE = True
    # Try to import decorators (may not be available in all versions)
    try:
        from langfuse.decorators import langfuse_context, observe
    except ImportError:
        langfuse_context = None  # type: ignore
        observe = None  # type: ignore
        logger.debug("Langfuse decorators not available (optional)")
except ImportError:
    LANGFUSE_AVAILABLE = False
    logger.warning("Langfuse SDK not installed. Install with: pip install langfuse")
    Langfuse = None  # type: ignore
    langfuse_context = None  # type: ignore
    observe = None  # type: ignore


def get_langfuse_client() -> Optional[Any]:
    """
    Initialize and return a Langfuse client if credentials are available.
    
    Returns:
        Langfuse client instance or None if not configured
    """
    if not LANGFUSE_AVAILABLE:
        logger.warning("Langfuse SDK not available")
        return None
    
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    
    if not public_key or not secret_key:
        logger.warning("Langfuse credentials not configured. Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY")
        return None
    
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    
    try:
        # Enable debug mode if LANGFUSE_DEBUG is set
        debug = os.getenv("LANGFUSE_DEBUG", "False").lower() == "true"
        client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
            debug=debug,
        )
        logger.info(f"Langfuse client initialized successfully (host: {host}, debug: {debug})")
        return client
    except Exception as e:
        logger.error(f"Failed to initialize Langfuse client: {e}", exc_info=True)
        return None


def get_langfuse_environment() -> str:
    """Get the Langfuse environment name (for prompt versioning)."""
    return os.getenv("LANGFUSE_ENVIRONMENT", "production")


# Global client instance (lazy initialization)
_langfuse_client: Optional[Any] = None


def get_langfuse() -> Optional[Any]:
    """Get or create the global Langfuse client instance."""
    global _langfuse_client
    if _langfuse_client is None:
        _langfuse_client = get_langfuse_client()
    return _langfuse_client


def fetch_prompt(
    prompt_name: str,
    environment: Optional[str] = None,
    version: Optional[int] = None,
    subject: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Fetch a prompt from Langfuse by name and environment.
    
    Args:
        prompt_name: Name of the prompt (e.g., 'question-generation', 'answer-marking')
        environment: Environment name (defaults to LANGFUSE_ENVIRONMENT)
        version: Specific version number (optional, uses latest if not specified)
        subject: Optional subject name for subject-specific prompts (e.g., 'Mathematics', 'Science')
                 If provided, will try '{prompt_name}-{subject_lowercase}' first, then fall back to base name
    
    Returns:
        Prompt dictionary with 'prompt' and 'config' keys, or None if not found
    """
    client = get_langfuse()
    if not client:
        logger.warning(f"Langfuse not available - cannot fetch prompt '{prompt_name}'")
        return None
    
    env = environment or get_langfuse_environment()
    
    # Try subject-specific prompt first if subject is provided
    prompt_to_fetch = prompt_name
    if subject:
        # Normalize subject name (e.g., "Mathematics" -> "mathematics")
        subject_normalized = subject.lower().replace(" ", "-")
        subject_specific_name = f"{prompt_name}-{subject_normalized}"
        prompt_to_fetch = subject_specific_name
        logger.info(f"Trying subject-specific prompt: '{subject_specific_name}' for subject '{subject}'")
    
    try:
        # Fetch prompt from Langfuse
        # Try without label first (most common), then with label if that fails
        prompt_obj = None
        try:
            if version:
                prompt_obj = client.get_prompt(prompt_to_fetch, version=version)
            else:
                prompt_obj = client.get_prompt(prompt_to_fetch)
        except Exception as e1:
            # If no-label fetch fails, try with label (for environment-specific prompts)
            logger.debug(f"Failed to fetch prompt '{prompt_to_fetch}' without label, trying with label '{env}': {e1}")
            try:
                if version:
                    prompt_obj = client.get_prompt(prompt_to_fetch, version=version, label=env)
                else:
                    prompt_obj = client.get_prompt(prompt_to_fetch, label=env)
            except Exception as e2:
                logger.warning(f"Failed to fetch prompt '{prompt_to_fetch}' with label '{env}': {e2}")
                raise e2
        
        if prompt_obj:
            # Extract the prompt string from the Prompt object
            # The Langfuse Prompt object structure may vary, try multiple ways to access it
            if hasattr(prompt_obj, 'prompt') and prompt_obj.prompt:
                prompt_template = str(prompt_obj.prompt)
            elif hasattr(prompt_obj, 'get_prompt'):
                prompt_template = str(prompt_obj.get_prompt())
            elif isinstance(prompt_obj, str):
                prompt_template = prompt_obj
            else:
                # Try to access as dict-like
                try:
                    prompt_template = str(prompt_obj.get('prompt', prompt_obj))
                except (AttributeError, TypeError):
                    prompt_template = str(prompt_obj)
            
            logger.info(f"Fetched prompt '{prompt_to_fetch}' from Langfuse (env: {env}, version: {version or 'latest'})")
            return {
                "prompt": prompt_template,
                "name": prompt_to_fetch,
                "environment": env,
            }
        else:
            # If subject-specific prompt not found and subject was provided, try base prompt
            if subject and prompt_to_fetch != prompt_name:
                logger.info(f"Subject-specific prompt '{prompt_to_fetch}' not found, trying base prompt '{prompt_name}'")
                try:
                    # Try without label first, then with label if that fails
                    prompt_obj = None
                    try:
                        if version:
                            prompt_obj = client.get_prompt(prompt_name, version=version)
                        else:
                            prompt_obj = client.get_prompt(prompt_name)
                    except Exception as e1:
                        # If no-label fetch fails, try with label
                        logger.debug(f"Failed to fetch base prompt '{prompt_name}' without label, trying with label '{env}': {e1}")
                        try:
                            if version:
                                prompt_obj = client.get_prompt(prompt_name, version=version, label=env)
                            else:
                                prompt_obj = client.get_prompt(prompt_name, label=env)
                        except Exception as e2:
                            logger.warning(f"Failed to fetch base prompt '{prompt_name}' with label '{env}': {e2}")
                            raise e2
                    
                    if prompt_obj:
                        if hasattr(prompt_obj, 'prompt') and prompt_obj.prompt:
                            prompt_template = str(prompt_obj.prompt)
                        elif hasattr(prompt_obj, 'get_prompt'):
                            prompt_template = str(prompt_obj.get_prompt())
                        elif isinstance(prompt_obj, str):
                            prompt_template = prompt_obj
                        else:
                            try:
                                prompt_template = str(prompt_obj.get('prompt', prompt_obj))
                            except (AttributeError, TypeError):
                                prompt_template = str(prompt_obj)
                        
                        logger.info(f"Fetched base prompt '{prompt_name}' from Langfuse (env: {env})")
                        return {
                            "prompt": prompt_template,
                            "name": prompt_name,
                            "environment": env,
                        }
                except Exception as e:
                    logger.warning(f"Failed to fetch base prompt '{prompt_name}': {e}")
            
            logger.warning(f"Prompt '{prompt_to_fetch}' not found in Langfuse (env: {env})")
            return None
    except Exception as e:
        logger.error(f"Failed to fetch prompt '{prompt_name}' from Langfuse: {e}")
        return None


def render_prompt(prompt_template: str, variables: Dict[str, Any]) -> str:
    """
    Render a prompt template with variables.
    
    Args:
        prompt_template: Prompt template string (supports {variable} syntax)
        variables: Dictionary of variables to substitute
    
    Returns:
        Rendered prompt string
    """
    try:
        return prompt_template.format(**variables)
    except KeyError as e:
        logger.error(f"Missing variable in prompt template: {e}")
        # Return template with missing variables marked
        return prompt_template


def create_trace(
    name: str,
    user_id: Optional[str] = None,
    revision_id: Optional[str] = None,
    run_id: Optional[str] = None,
    question_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Any]:
    """
    Create a Langfuse trace for observability.
    
    Args:
        name: Name of the trace (e.g., 'question-generation', 'answer-marking')
        user_id: User ID (if authenticated)
        revision_id: Revision ID
        run_id: Run ID
        question_id: Question ID (for answer marking)
        metadata: Additional metadata dictionary
    
    Returns:
        Langfuse span object or None if Langfuse not available
    """
    client = get_langfuse()
    if not client:
        return None
    
    trace_metadata = {}
    
    if user_id:
        trace_metadata["user_id"] = user_id
    if revision_id:
        trace_metadata["revision_id"] = revision_id
    if run_id:
        trace_metadata["run_id"] = run_id
    if question_id:
        trace_metadata["question_id"] = question_id
    if metadata:
        trace_metadata.update(metadata)
    
    try:
        # Use start_span to create a trace (top-level span acts as trace)
        # The new Langfuse SDK uses spans, where the top-level span is the trace
        span = client.start_span(
            name=name,
            metadata=trace_metadata,
        )
        logger.info(f"Created Langfuse trace: name='{name}' (user_id: {user_id}, revision_id: {revision_id}, run_id: {run_id})")
        logger.debug(f"Trace span object: {span}, type: {type(span)}")
        # Don't flush immediately - wait until generation is complete
        # This ensures the trace stays open for child observations
        return span
    except Exception as e:
        logger.error(f"Failed to create Langfuse trace: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        return None


def create_generation(
    trace: Any,
    name: str,
    model: str,
    input_data: Dict[str, Any],
    output: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Any]:
    """
    Create a generation span within a trace.
    
    Args:
        trace: Langfuse span/trace object
        name: Name of the generation (e.g., 'openai-call')
        model: Model name used
        input_data: Input data (messages, etc.)
        output: Output text
        metadata: Additional metadata
    
    Returns:
        Langfuse generation object or None
    """
    if not trace:
        return None
    
    try:
        # Use start_observation with as_type='generation' (recommended approach)
        # Set input and output directly when creating the observation
        logger.debug(f"Creating Langfuse generation: {name}, model: {model}")
        logger.debug(f"Input data type: {type(input_data)}, keys: {list(input_data.keys()) if isinstance(input_data, dict) else 'N/A'}")
        logger.debug(f"Output type: {type(output)}, length: {len(output) if isinstance(output, str) else 'N/A'}")
        
        # Create observation first
        generation = trace.start_observation(
            name=name,
            as_type="generation",
            model=model,
        )
        
        # Then update with input, output, and metadata
        # This pattern seems more reliable for ensuring data is recorded
        generation.update(
            input=input_data,
            output=output,
            metadata=metadata or {},
        )
        
        # End the generation to mark it as complete
        generation.end()
        logger.info(f"Created Langfuse generation: name='{name}', model='{model}' (input: {len(str(input_data))} chars, output: {len(str(output))} chars)")
        logger.debug(f"Generation object: {generation}, type: {type(generation)}")
        
        # Explicitly set trace input/output from the generation
        # According to Langfuse FAQ: trace input/output should be set explicitly
        # https://langfuse.com/faq/all/empty-trace-input-and-output
        try:
            trace.update_trace(
                input=input_data,
                output=output,
            )
            logger.debug("Updated trace input/output from generation")
        except Exception as trace_update_error:
            logger.warning(f"Failed to update trace input/output: {trace_update_error}")
        
        # Flush to ensure generation is sent immediately
        client = get_langfuse()
        if client:
            try:
                client.flush()
                logger.debug("Flushed Langfuse client after generation")
            except Exception as flush_error:
                logger.warning(f"Failed to flush Langfuse client after generation: {flush_error}")
        return generation
    except Exception as e:
        logger.error(f"Failed to create Langfuse generation: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        return None

