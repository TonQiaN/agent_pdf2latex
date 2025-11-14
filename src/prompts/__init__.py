"""Prompt management for PDF to LaTeX workflow"""

# New dynamic prompts (LangChain 1.0 style)
from src.prompts.dynamic_prompts import build_dynamic_system_prompt

__all__ = [
    # Dynamic prompts (recommended)
    "build_dynamic_system_prompt",
]

