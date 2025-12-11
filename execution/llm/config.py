"""
LLM Configuration

Handles API keys and model configuration for LLM operations.
Uses LiteLLM for model-agnostic API calls.
"""

import os
from dotenv import load_dotenv

load_dotenv(override=True)

# Model configuration
DEFAULT_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
DEFAULT_BATCH_SIZE = int(os.getenv("LLM_BATCH_SIZE", "20"))

# API Keys (loaded from .env)
# OPENAI_API_KEY - for OpenAI models
# ANTHROPIC_API_KEY - for Claude models  
# GEMINI_API_KEY - for Google models

def get_model_config():
    """Get current model configuration."""
    return {
        "model": DEFAULT_MODEL,
        "batch_size": DEFAULT_BATCH_SIZE
    }
