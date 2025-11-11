"""
LLM Clients for import_v2
复用自 marking_v2，扩展 Function Calling 支持
"""
from .base import (
    BaseModelClient, LLMMessage, LLMResponse, MessageContent, MessageRole, ContentType,
    LLMClientConfig, LLMClientError, RateLimitError, AuthenticationError,
    InvalidRequestError, ModelNotAvailableError
)
from .openai_client import OpenAIClient
from .google_client import GoogleClient
from .xai_client import XaiClient
from .client_manager import ClientManager

__all__ = [
    # Base classes and models
    "BaseModelClient",
    "LLMMessage",
    "LLMResponse",
    "MessageContent",
    "MessageRole",
    "ContentType",
    "LLMClientConfig",

    # Exceptions
    "LLMClientError",
    "RateLimitError",
    "AuthenticationError",
    "InvalidRequestError",
    "ModelNotAvailableError",

    # Client implementations
    "OpenAIClient",
    "GoogleClient",
    "XaiClient",

    # Client manager
    "ClientManager",
]