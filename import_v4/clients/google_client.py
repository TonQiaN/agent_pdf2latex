import asyncio
import base64
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Union, Dict, Any, Iterator, AsyncIterator, Optional, Sequence

from google import genai
from src.services.utilities import load_environment_variables
import httpx
import os

# 禁用httpx的HTTP请求日志
logging.getLogger("httpx").setLevel(logging.WARNING)

from .base import (
    BaseModelClient, LLMMessage, LLMResponse, MessageContent, MessageRole, ContentType,
    LLMClientConfig, LLMClientError, RateLimitError, AuthenticationError, 
    InvalidRequestError, ModelNotAvailableError
)


class GoogleClient(BaseModelClient):
    """Google client implementation."""
    
    # Token pricing per 1K tokens (as of 2024)
    TOKEN_PRICING = {
        "gemini-2.5-pro": {"prompt": 0.0025, "completion": 0.015},
        "gemini-2.5-flash": {"prompt": 0.0003, "completion": 0.0025},
    }
    
    def __init__(
        self, 
        model_name: Optional[str] = "gemini-2.5-pro",
        config: Optional[LLMClientConfig] = None,
        **kwargs
    ):
        if model_name is None:
            model_name = "gemini-2.5-pro"
        
        if model_name not in self.TOKEN_PRICING:
            raise ValueError(f"Invalid model name: {model_name}")
        
        self.model_name = model_name
        super().__init__("Google", model_name, config, **kwargs)

        load_environment_variables()

        self.client = genai.Client()
        
        # For async operations
        self._async_model = None
        # httpx async client setup
        if not self.config.api_base:
            self.config.api_base = "https://generativelanguage.googleapis.com/v1beta"
        self._api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        self.async_client = httpx.AsyncClient(timeout=self.config.timeout, headers={
            "Content-Type": "application/json",
        })
    
    def _convert_to_gemini_format(self, messages: List[LLMMessage]) -> List[Dict[str, Any]]:
        """Convert LLMMessage objects to Gemini API format."""
        gemini_messages = []
        
        for msg in messages:
            role = "user" if msg.role == MessageRole.USER else "model"
            
            # Handle content
            if isinstance(msg.content, str):
                gemini_msg = {
                    "role": role,
                    "parts": [{"text": msg.content}]
                }
            else:
                parts = []
                for item in msg.content:
                    if item.type == ContentType.TEXT:
                        parts.append({"text": item.text})
                    elif item.type == ContentType.IMAGE:
                        parts.append({
                            "inline_data": {
                                "mime_type": "image/png",
                                "data": item.image_base64
                            }
                        })
                    elif item.type == ContentType.IMAGE_URL:
                        # For image URLs, we might need to download and convert to base64
                        # For now, just include as text description
                        parts.append({"text": f"[Image URL: {item.image_url}]"})
                
                gemini_msg = {
                    "role": role,
                    "parts": parts
                }
            
            gemini_messages.append(gemini_msg)
        
        return gemini_messages
    
    async def aquery(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        **kwargs: Any
    ) -> LLMResponse:
        """Asynchronous query to Gemini."""
        try:
            # Convert messages to HTTP API format for async requests
            gemini_messages = self._convert_to_gemini_format(messages)
            
            # Prepare request payload
            contents = []
            for msg in gemini_messages:
                contents.append({
                    "role": msg["role"],
                    "parts": msg["parts"]
                })
            
            payload = {
                "contents": contents,
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens or 1000,
                    **kwargs
                }
            }
            
            # Make async HTTP request
            url = f"{self.config.api_base}/models/{self.model_name}:generateContent"
            headers = {"x-goog-api-key": self._api_key}
            
            response = await self.async_client.post(
                url, 
                json=payload, 
                headers=headers,
                timeout=self.config.timeout
            )
            response.raise_for_status()
            
            response_data = response.json()
            
            # Convert to LLMResponse
            usage = None
            if "usageMetadata" in response_data:
                usage_data = response_data["usageMetadata"]
                usage = {
                    "prompt_tokens": usage_data.get("promptTokenCount", 0),
                    "completion_tokens": usage_data.get("candidatesTokenCount", 0),
                    "total_tokens": usage_data.get("totalTokenCount", 0)
                }
            
            content = ""
            if "candidates" in response_data and response_data["candidates"]:
                candidate = response_data["candidates"][0]
                if "content" in candidate and "parts" in candidate["content"]:
                    parts = candidate["content"]["parts"]
                    if parts and "text" in parts[0]:
                        content = parts[0]["text"]
            
            llm_response = LLMResponse(
                content=content,
                usage=usage,
                model=self.model_name,
                finish_reason=response_data.get("candidates", [{}])[0].get("finishReason"),
                metadata={"safetyRatings": response_data.get("candidates", [{}])[0].get("safetyRatings", [])}
            )
            
            # Update metrics
            if llm_response.usage:
                cost = self.calculate_cost(llm_response.usage)
                self.update_metrics(llm_response.usage["total_tokens"], cost)
            
            return llm_response
                
        except Exception as e:
            raise self.format_error(e)
    
    def calculate_cost(self, usage: Dict[str, int]) -> float:
        """Calculate cost based on Gemini pricing."""
        model_key = self.model_name.lower()
        
        # Find matching pricing model
        pricing = None
        for model in self.TOKEN_PRICING:
            if model in model_key:
                pricing = self.TOKEN_PRICING[model]
                break
        
        if not pricing:
            # Default pricing for unknown models
            pricing = self.TOKEN_PRICING["gemini-1.5-pro"]
        
        prompt_cost = (usage.get("prompt_tokens", 0) / 1000) * pricing["prompt"]
        completion_cost = (usage.get("completion_tokens", 0) / 1000) * pricing["completion"]
        
        return prompt_cost + completion_cost
    
    def format_error(self, error: Exception) -> LLMClientError:
        """Convert Gemini exceptions to standard LLMClientError types."""
        error_str = str(error).lower()
        
        if "authentication" in error_str or "api key" in error_str:
            return AuthenticationError(str(error))
        elif "rate limit" in error_str or "quota" in error_str:
            return RateLimitError(str(error))
        elif "invalid" in error_str or "bad request" in error_str:
            return InvalidRequestError(str(error))
        elif "model" in error_str and "not found" in error_str:
            return ModelNotAvailableError(str(error))
        else:
            return super().format_error(error)
    
    async def close(self):
        """Close the async client."""
        if hasattr(self.async_client, 'aclose'):
            await self.async_client.aclose()
