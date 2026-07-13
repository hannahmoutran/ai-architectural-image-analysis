# model_pricing.py
"""
Centralized model pricing configuration for OpenAI and Anthropic models.
Updated as of January 2026 - verify current pricing at:
  - https://openai.com/pricing
  - https://docs.anthropic.com/en/docs/about-claude/pricing

Prices are per 1M tokens, converted to per 1K for calculation.
Standard tier pricing is used as default.
"""

MODEL_PRICING = {
    # ===================
    # GOOGLE GEMINI MODELS
    # ===================

    # Gemini 3 Pro Preview
    "gemini-3-pro-preview": {
        "input_per_1k": 0.002,    # $2 per 1M (<200k tokens)
        "output_per_1k": 0.012,   # $12 per 1M (<200k tokens)
        "batch_discount": 0.5
    },

    # Gemini 3 Flash Preview
    "gemini-3-flash-preview": {
        "input_per_1k": 0.0005,   # $0.50 per 1M
        "output_per_1k": 0.003,   # $3 per 1M
        "batch_discount": 0.5
    },

    # Gemini 3 Pro Image Preview (Nano Banana Pro)
    "gemini-3-pro-image-preview": {
        "input_per_1k": 0.002,    # $2 per 1M (Text Input)
        "output_per_1k": 0.012,   # Varies for image output
        "batch_discount": 0.5
    },

    # ===================
    # ANTHROPIC MODELS
    # ===================

    # Claude Opus 4.5
    "claude-opus-4-5-20250514": {
        "input_per_1k": 0.005,    # $5 per 1M
        "output_per_1k": 0.025,   # $25 per 1M
        "batch_discount": 0.5
    },

    # Claude Opus 4.1
    "claude-opus-4-1-20250414": {
        "input_per_1k": 0.015,    # $15 per 1M
        "output_per_1k": 0.075,   # $75 per 1M
        "batch_discount": 0.5
    },

    # Claude Opus 4
    "claude-opus-4-20250514": {
        "input_per_1k": 0.015,    # $15 per 1M
        "output_per_1k": 0.075,   # $75 per 1M
        "batch_discount": 0.5
    },

    # Claude Sonnet 4.5
    "claude-sonnet-4-5-20250514": {
        "input_per_1k": 0.003,    # $3 per 1M
        "output_per_1k": 0.015,   # $15 per 1M
        "batch_discount": 0.5
    },
    "claude-sonnet-4-5-20250929": {
        "input_per_1k": 0.003,    # $3 per 1M
        "output_per_1k": 0.015,   # $15 per 1M
        "batch_discount": 0.5
    },

    # Claude Sonnet 4
    "claude-sonnet-4-20250514": {
        "input_per_1k": 0.003,    # $3 per 1M
        "output_per_1k": 0.015,   # $15 per 1M
        "batch_discount": 0.5
    },

    # Claude Haiku 4.5
    "claude-haiku-4-5-20250514": {
        "input_per_1k": 0.001,    # $1 per 1M
        "output_per_1k": 0.005,   # $5 per 1M
        "batch_discount": 0.5
    },

    # Claude Haiku 3.5
    "claude-3-5-haiku-20241022": {
        "input_per_1k": 0.0008,   # $0.80 per 1M
        "output_per_1k": 0.004,   # $4 per 1M
        "batch_discount": 0.5
    },

    # Claude Haiku 3
    "claude-3-haiku-20240307": {
        "input_per_1k": 0.00025,  # $0.25 per 1M
        "output_per_1k": 0.00125, # $1.25 per 1M
        "batch_discount": 0.5
    },

    # ===================
    # OPENAI MODELS
    # ===================

    # GPT-5.6 Luna
    "gpt-5.6-luna": {
        "input_per_1k": 0.001,    # $1.00 per 1M (cached input: $0.10 per 1M)
        "output_per_1k": 0.006,   # $6.00 per 1M
        "batch_discount": 0.5
    },

    # GPT-5.2 models
    "gpt-5.2": {
        "input_per_1k": 0.00175,  # $1.75 per 1M
        "output_per_1k": 0.014,   # $14.00 per 1M
        "batch_discount": 0.5
    },

    # GPT-5.1 models
    "gpt-5.1": {
        "input_per_1k": 0.00125,  # $1.25 per 1M
        "output_per_1k": 0.01,    # $10.00 per 1M
        "batch_discount": 0.5
    },

    # GPT-5 models
    "gpt-5": {
        "input_per_1k": 0.00125,  # $1.25 per 1M
        "output_per_1k": 0.01,    # $10.00 per 1M
        "batch_discount": 0.5
    },

    # GPT-5-mini models
    "gpt-5-mini": {
        "input_per_1k": 0.00025,  # $0.25 per 1M
        "output_per_1k": 0.002,   # $2.00 per 1M
        "batch_discount": 0.5
    },

    # GPT-5-nano models
    "gpt-5-nano": {
        "input_per_1k": 0.00005,  # $0.05 per 1M
        "output_per_1k": 0.0004,  # $0.40 per 1M
        "batch_discount": 0.5
    },

    # GPT-5-pro models (no batch discount listed)
    "gpt-5.2-pro": {
        "input_per_1k": 0.021,    # $21.00 per 1M
        "output_per_1k": 0.168,   # $168.00 per 1M
        "batch_discount": 0.5
    },
    "gpt-5-pro": {
        "input_per_1k": 0.015,    # $15.00 per 1M
        "output_per_1k": 0.12,    # $120.00 per 1M
        "batch_discount": 0.5
    },

    # GPT-4.1 models
    "gpt-4.1": {
        "input_per_1k": 0.002,    # $2.00 per 1M
        "output_per_1k": 0.008,   # $8.00 per 1M
        "batch_discount": 0.5
    },
    "gpt-4.1-2025-04-14": {
        "input_per_1k": 0.002,    # $2.00 per 1M
        "output_per_1k": 0.008,   # $8.00 per 1M
        "batch_discount": 0.5
    },

    # GPT-4.1-mini models
    "gpt-4.1-mini": {
        "input_per_1k": 0.0004,   # $0.40 per 1M
        "output_per_1k": 0.0016,  # $1.60 per 1M
        "batch_discount": 0.5
    },
    "gpt-4.1-mini-2025-04-14": {
        "input_per_1k": 0.0004,   # $0.40 per 1M
        "output_per_1k": 0.0016,  # $1.60 per 1M
        "batch_discount": 0.5
    },

    # GPT-4.1-nano models
    "gpt-4.1-nano": {
        "input_per_1k": 0.0001,   # $0.10 per 1M
        "output_per_1k": 0.0004,  # $0.40 per 1M
        "batch_discount": 0.5
    },
    "gpt-4.1-nano-2025-04-14": {
        "input_per_1k": 0.0001,   # $0.10 per 1M
        "output_per_1k": 0.0004,  # $0.40 per 1M
        "batch_discount": 0.5
    },

    # GPT-4o models
    "gpt-4o": {
        "input_per_1k": 0.0025,   # $2.50 per 1M
        "output_per_1k": 0.01,    # $10.00 per 1M
        "batch_discount": 0.5
    },
    "gpt-4o-2024-08-06": {
        "input_per_1k": 0.0025,   # $2.50 per 1M
        "output_per_1k": 0.01,    # $10.00 per 1M
        "batch_discount": 0.5
    },
    "gpt-4o-2024-05-13": {
        "input_per_1k": 0.005,    # $5.00 per 1M
        "output_per_1k": 0.015,   # $15.00 per 1M
        "batch_discount": 0.5
    },

    # GPT-4o-mini models
    "gpt-4o-mini": {
        "input_per_1k": 0.00015,  # $0.15 per 1M
        "output_per_1k": 0.0006,  # $0.60 per 1M
        "batch_discount": 0.5
    },
    "gpt-4o-mini-2024-07-18": {
        "input_per_1k": 0.00015,  # $0.15 per 1M
        "output_per_1k": 0.0006,  # $0.60 per 1M
        "batch_discount": 0.5
    },

    # O-series reasoning models
    "o1": {
        "input_per_1k": 0.015,    # $15.00 per 1M
        "output_per_1k": 0.06,    # $60.00 per 1M
        "batch_discount": 0.5
    },
    "o1-pro": {
        "input_per_1k": 0.15,     # $150.00 per 1M
        "output_per_1k": 0.6,     # $600.00 per 1M
        "batch_discount": 0.5
    },
    "o1-mini": {
        "input_per_1k": 0.0011,   # $1.10 per 1M
        "output_per_1k": 0.0044,  # $4.40 per 1M
        "batch_discount": 0.5
    },
    "o3": {
        "input_per_1k": 0.002,    # $2.00 per 1M
        "output_per_1k": 0.008,   # $8.00 per 1M
        "batch_discount": 0.5
    },
    "o3-pro": {
        "input_per_1k": 0.02,     # $20.00 per 1M
        "output_per_1k": 0.08,    # $80.00 per 1M
        "batch_discount": 0.5
    },
    "o3-mini": {
        "input_per_1k": 0.0011,   # $1.10 per 1M
        "output_per_1k": 0.0044,  # $4.40 per 1M
        "batch_discount": 0.5
    },
    "o4-mini": {
        "input_per_1k": 0.0011,   # $1.10 per 1M
        "output_per_1k": 0.0044,  # $4.40 per 1M
        "batch_discount": 0.5
    },
}

def calculate_cost(model_name, prompt_tokens, completion_tokens, is_batch=False):
    """
    Calculate the cost for a given model and token usage.

    Args:
        model_name (str): The model name
        prompt_tokens (int): Number of input tokens
        completion_tokens (int): Number of output tokens
        is_batch (bool): Whether this was a batch request (for discount)

    Returns:
        float: Total cost in USD
    """
    if model_name not in MODEL_PRICING:
        print(f"Warning: Unknown model '{model_name}', using GPT-4o-mini pricing as fallback")
        model_name = "gpt-4o-mini"

    pricing = MODEL_PRICING[model_name]

    input_cost = (prompt_tokens / 1000) * pricing["input_per_1k"]
    output_cost = (completion_tokens / 1000) * pricing["output_per_1k"]
    total_cost = input_cost + output_cost

    if is_batch:
        total_cost *= pricing["batch_discount"]

    return total_cost

def get_model_info(model_name):
    """
    Get pricing information for a model.

    Args:
        model_name (str): The model name

    Returns:
        dict: Pricing information
    """
    if model_name not in MODEL_PRICING:
        print(f"Warning: Unknown model '{model_name}'")
        return None

    return MODEL_PRICING[model_name]

def estimate_cost(model_name, estimated_prompt_tokens, estimated_completion_tokens, is_batch=False):
    """
    Estimate cost before making API calls.

    Args:
        model_name (str): The model name
        estimated_prompt_tokens (int): Estimated input tokens
        estimated_completion_tokens (int): Estimated output tokens
        is_batch (bool): Whether this will be a batch request

    Returns:
        dict: Cost breakdown
    """
    regular_cost = calculate_cost(model_name, estimated_prompt_tokens, estimated_completion_tokens, is_batch=False)
    batch_cost = calculate_cost(model_name, estimated_prompt_tokens, estimated_completion_tokens, is_batch=True)

    return {
        "regular_cost": regular_cost,
        "batch_cost": batch_cost,
        "savings": regular_cost - batch_cost,
        "savings_percentage": ((regular_cost - batch_cost) / regular_cost) * 100 if regular_cost > 0 else 0
    }
