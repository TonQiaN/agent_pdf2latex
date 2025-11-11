"""
OpenAI Client 实现
复用自 marking_v2，扩展 Function Calling 支持
"""
import asyncio
import os
import time
import logging
from typing import List, Union, Dict, Any, Iterator, AsyncIterator, Optional, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
import openai
from openai import OpenAI, AsyncOpenAI

# 禁用httpx的HTTP请求日志
logging.getLogger("httpx").setLevel(logging.WARNING)

from .base import (
    BaseModelClient, LLMMessage, LLMResponse, MessageContent, MessageRole, ContentType,
    LLMClientConfig, LLMClientError, RateLimitError, AuthenticationError,
    InvalidRequestError, ModelNotAvailableError
)


class OpenAIClient(BaseModelClient):
    """OpenAI client implementation supporting GPT models with Function Calling."""

    # Token pricing per 1K tokens (as of 2024)
    TOKEN_PRICING = {
        "gpt-4o": {"prompt": 0.0025, "completion": 0.010},
        "gpt-4-turbo": {"prompt": 0.010, "completion": 0.030},
        "gpt-4-vision-preview": {"prompt": 0.010, "completion": 0.030},
        "gpt-5": {"prompt": 0.00125, "completion": 0.010},
        "gpt-5-mini": {"prompt": 0.00025, "completion": 0.0020},
        "gpt-5-nano": {"prompt": 0.00005, "completion": 0.00040},
    }

    def __init__(
        self,
        model_name: Optional[str] = "gpt-5",  # 默认使用 GPT-5
        config: Optional[LLMClientConfig] = None,
        **kwargs
    ):
        if model_name is None:
            model_name = "gpt-5"

        self.model_name = model_name
        super().__init__("OpenAI", model_name, config, **kwargs)

        # Load environment variables for API key
        from src.services.utilities import load_environment_variables
        load_environment_variables()

        # Initialize OpenAI clients
        client_kwargs = {
            "api_key": self.config.api_key or os.getenv("OPENAI_API_KEY"),
            "timeout": self.config.timeout,
        }

        if self.config.api_base:
            client_kwargs["base_url"] = self.config.api_base

        self.client = OpenAI(**client_kwargs)
        self.async_client = AsyncOpenAI(**client_kwargs)

    def _convert_to_openai_format(self, messages: List[LLMMessage]) -> List[Dict[str, Any]]:
        """Convert LLMMessage objects to OpenAI API format."""
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

    def _format_content(self, content: Union[str, List[MessageContent]]) -> Union[str, List[Dict[str, Any]]]:
        """Format content for OpenAI API (supports Vision and File Reference)."""
        if isinstance(content, str):
            return content

        formatted_content = []
        for item in content:
            if item.type == ContentType.TEXT:
                formatted_content.append({
                    "type": "text",
                    "text": item.text
                })
            elif item.type == ContentType.IMAGE_URL:
                formatted_content.append({
                    "type": "image_url",
                    "image_url": {"url": item.image_url}
                })
            elif item.type == ContentType.IMAGE:
                formatted_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{item.image_base64}"}
                })
            elif item.type == ContentType.FILE:
                # ⭐ 新增：文件引用
                # 正确格式：{"type": "file", "file": {"file_id": "..."}}
                formatted_content.append({
                    "type": "file",
                    "file": {"file_id": item.file_id}
                })

        return formatted_content

    def _create_response(self, openai_response) -> LLMResponse:
        """Convert OpenAI response to LLMResponse."""
        usage = None
        if hasattr(openai_response, 'usage') and openai_response.usage:
            usage = {
                "prompt_tokens": openai_response.usage.prompt_tokens,
                "completion_tokens": openai_response.usage.completion_tokens,
                "total_tokens": openai_response.usage.total_tokens
            }

        message = openai_response.choices[0].message

        # ⭐ 处理 function_call
        function_call = None
        if hasattr(message, 'function_call') and message.function_call:
            function_call = {
                "name": message.function_call.name,
                "arguments": message.function_call.arguments
            }

        return LLMResponse(
            content=message.content,
            usage=usage,
            model=openai_response.model,
            finish_reason=openai_response.choices[0].finish_reason,
            function_call=function_call,  # ⭐ 新增
            metadata={
                "created": getattr(openai_response, 'created', None),
                "system_fingerprint": getattr(openai_response, 'system_fingerprint', None)
            }
        )

    async def aquery(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        functions: Optional[List[Dict]] = None,  # ⭐ 新增
        function_call: Optional[Union[str, Dict]] = "auto",  # ⭐ 新增
        **kwargs: Any
    ) -> LLMResponse:
        """
        Asynchronous query to OpenAI with Function Calling support.

        ⭐ 扩展：支持 functions 和 function_call 参数
        """
        openai_messages = self._convert_to_openai_format(messages)

        params = {
            "model": self.model_name,
            "messages": openai_messages,
            **kwargs
        }

        # 只有在明确设置了temperature时才添加
        if "temperature" in kwargs or temperature != 0.0:
            params["temperature"] = temperature

        # 处理 max_tokens 参数：
        # - GPT-5 和新模型使用 max_completion_tokens
        # - 旧模型使用 max_tokens
        # 如果 kwargs 中已经有这些参数之一，优先使用 kwargs 中的
        if max_tokens:
            if "max_completion_tokens" not in kwargs and "max_tokens" not in kwargs:
                # 根据模型名称决定使用哪个参数
                if self.model_name.startswith("gpt-5") or self.model_name.startswith("o1"):
                    params["max_completion_tokens"] = max_tokens
                else:
                    params["max_tokens"] = max_tokens

        # ⭐ 添加 function calling 支持
        if functions:
            params["functions"] = functions
            params["function_call"] = function_call

        try:
            response = await self.async_client.chat.completions.create(**params)
            llm_response = self._create_response(response)

            # Update metrics
            if llm_response.usage:
                cost = self.calculate_cost(llm_response.usage)
                self.update_metrics(llm_response.usage["total_tokens"], cost)

            return llm_response

        except Exception as e:
            raise self.format_error(e)

    def calculate_cost(self, usage: Dict[str, int]) -> float:
        """Calculate cost based on OpenAI pricing."""
        model_key = self.model_name.lower()

        # Find matching pricing model
        pricing = None
        for model in self.TOKEN_PRICING:
            if model in model_key:
                pricing = self.TOKEN_PRICING[model]
                break

        if not pricing:
            # Default pricing for unknown models
            pricing = self.TOKEN_PRICING["gpt-4o"]

        prompt_cost = (usage.get("prompt_tokens", 0) / 1000) * pricing["prompt"]
        completion_cost = (usage.get("completion_tokens", 0) / 1000) * pricing["completion"]

        return prompt_cost + completion_cost

    def format_error(self, error: Exception) -> LLMClientError:
        """Convert OpenAI exceptions to standard LLMClientError types."""
        if isinstance(error, openai.RateLimitError):
            return RateLimitError(str(error))
        elif isinstance(error, openai.AuthenticationError):
            return AuthenticationError(str(error))
        elif isinstance(error, openai.BadRequestError):
            return InvalidRequestError(str(error))
        elif isinstance(error, openai.NotFoundError):
            return ModelNotAvailableError(str(error))
        else:
            return super().format_error(error)

    async def close(self):
        """Close the async client."""
        if hasattr(self.async_client, 'close'):
            await self.async_client.close()