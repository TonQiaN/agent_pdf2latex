"""LangChain agent middleware for PDF to LaTeX workflow"""

# Legacy middleware (from openai.ipynb)
# from src.middleware.long_prompt import LongPromptMiddleware
# from src.middleware.output_validation import OutputValidationMiddleware

# New dynamic middleware (LangChain 1.0 style - recommended)
from src.middleware.dynamic_prompt_middleware import (
    DynamicPromptWithRetryMiddleware,
    TokenBudgetMiddleware,
    ToolControlMiddleware,
)

__all__ = [
    # Dynamic middleware (recommended)
    "DynamicPromptWithRetryMiddleware",
    "TokenBudgetMiddleware",
    "ToolControlMiddleware",
]

