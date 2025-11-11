import asyncio
import json
import os
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Union, Dict, Any, Iterator, Optional, Sequence

import httpx
from src.services.utilities import load_environment_variables

# 禁用httpx的HTTP请求日志
logging.getLogger("httpx").setLevel(logging.WARNING)

from .base import (
    BaseModelClient, LLMMessage, LLMResponse, MessageContent, MessageRole, ContentType,
    LLMClientConfig, LLMClientError, RateLimitError, AuthenticationError, 
    InvalidRequestError, ModelNotAvailableError
)


class XaiClient(BaseModelClient):
    """xAI Grok client implementation."""
    
    # Token pricing per 1K tokens (estimated, as official pricing may vary)
    TOKEN_PRICING = {
        "grok-4": {"prompt": 0.003, "completion": 0.015}
    }
    
    def __init__(
        self, 
        model_name: Optional[str] = "grok-4",
        config: Optional[LLMClientConfig] = None,
        **kwargs
    ):
        if model_name is None:
            model_name = "grok-4"

        if model_name not in self.TOKEN_PRICING:
            raise ValueError(f"Invalid model name: {model_name}")
        
        load_environment_variables()
        self.model_name = model_name
        super().__init__("Xai", model_name, config, **kwargs)
        
        # Ensure default API base for httpx async client
        if not self.config.api_base:
            self.config.api_base = "https://api.x.ai/v1"
        
        # Initialize Async HTTP client with auth header
        api_key = os.getenv("XAI_API_KEY")
        headers = {
            "Authorization": f"Bearer {api_key}" if api_key else "",
            "Content-Type": "application/json",
        }
        self.async_client = httpx.AsyncClient(timeout=self.config.timeout, headers=headers)
    
    def _convert_to_openai_format(self, messages: List[LLMMessage]) -> List[Dict[str, Any]]:
        """Convert LLMMessage objects to OpenAI-compatible format for XAI API."""
        openai_messages = []
        
        for msg in messages:
            openai_msg = {
                "role": msg.role.value,
                "content": self._format_content(msg.content)
            }
            
            if msg.name:
                openai_msg["name"] = msg.name
                
            openai_messages.append(openai_msg)
        
        return openai_messages
    
    def _format_content(self, content: Union[str, List[MessageContent]]) -> str:
        """Format content for XAI API - simplified to text only for now."""
        if isinstance(content, str):
            return content
        
        # Convert multi-modal content to text only
        # Note: XAI Grok may not support images yet, so we convert to text descriptions
        text_parts = []
        for item in content:
            if item.type == ContentType.TEXT:
                text_parts.append(item.text)
            elif item.type == ContentType.IMAGE_URL:
                text_parts.append(f"[Image from URL: {item.image_url}]")
            elif item.type == ContentType.IMAGE:
                text_parts.append("[Base64 Image provided - please analyze the image content for evaluation]")
        
        return " ".join(text_parts) if text_parts else ""
    
    def _create_response(self, xai_response_data: Dict[str, Any]) -> LLMResponse:
        """Convert XAI response to LLMResponse."""
        choice = xai_response_data["choices"][0]
        message = choice["message"]
        
        usage = None
        if "usage" in xai_response_data:
            usage_data = xai_response_data["usage"]
            usage = {
                "prompt_tokens": usage_data.get("prompt_tokens", 0),
                "completion_tokens": usage_data.get("completion_tokens", 0),
                "total_tokens": usage_data.get("total_tokens", 0)
            }
        
        return LLMResponse(
            content=message["content"],
            usage=usage,
            model=xai_response_data.get("model", self.model_name),
            finish_reason=choice.get("finish_reason"),
            metadata={
                "created": xai_response_data.get("created"),
                "id": xai_response_data.get("id"),
                "object": xai_response_data.get("object")
            }
        )
    
    async def aquery(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        **kwargs: Any
    ) -> LLMResponse:
        """Asynchronous query to XAI."""
        # Convert messages to OpenAI-compatible format
        openai_messages = self._convert_to_openai_format(messages)
        
        payload = {
            "model": self.model_name,
            "messages": openai_messages,
            "temperature": temperature,
            **kwargs
        }
        
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        url = f"{self.config.api_base}/chat/completions"
        
        try:
            response = await self.async_client.post(url, json=payload, timeout=self.config.timeout)
            response.raise_for_status()
            response_data = response.json()
            llm_response = self._create_response(response_data)
            
            # Update metrics
            if llm_response.usage:
                cost = self.calculate_cost(llm_response.usage)
                self.update_metrics(llm_response.usage["total_tokens"], cost)
            
            return llm_response
                
        except Exception as e:
            raise self.format_error(e)
    
    def calculate_cost(self, usage: Dict[str, int]) -> float:
        """Calculate cost based on XAI pricing."""
        model_key = self.model_name.lower()
        
        # Find matching pricing model
        pricing = None
        for model in self.TOKEN_PRICING:
            if model in model_key:
                pricing = self.TOKEN_PRICING[model]
                break
        
        if not pricing:
            # Default pricing for unknown models
            pricing = self.TOKEN_PRICING["grok-beta"]
        
        prompt_cost = (usage.get("prompt_tokens", 0) / 1000) * pricing["prompt"]
        completion_cost = (usage.get("completion_tokens", 0) / 1000) * pricing["completion"]
        
        return prompt_cost + completion_cost
    
    def format_error(self, error: Exception) -> LLMClientError:
        """Convert HTTP/XAI exceptions to standard LLMClientError types."""
        if isinstance(error, httpx.HTTPStatusError):
            status_code = error.response.status_code
            error_content = error.response.text
            
            if status_code == 401:
                return AuthenticationError(f"Authentication failed: {error_content}")
            elif status_code == 429:
                return RateLimitError(f"Rate limit exceeded: {error_content}")
            elif status_code == 400:
                return InvalidRequestError(f"Invalid request: {error_content}")
            elif status_code == 404:
                return ModelNotAvailableError(f"Model not found: {error_content}")
            else:
                return LLMClientError(f"HTTP {status_code}: {error_content}")
        
        elif isinstance(error, httpx.TimeoutException):
            return LLMClientError(f"Request timeout: {str(error)}")
        
        elif isinstance(error, httpx.ConnectError):
            return LLMClientError(f"Connection error: {str(error)}")
        
        else:
            return super().format_error(error)
    
    async def close(self):
        """Close the HTTP clients."""
        if hasattr(self, "async_client") and self.async_client is not None:
            await self.async_client.aclose()
