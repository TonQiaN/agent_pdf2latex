"""
LLM客户端基础架构
复用自 marking_v2，扩展 Function Calling 支持
"""
import logging
import threading
from abc import ABC, abstractmethod
from enum import Enum
from typing import Literal, Union, Dict, List, Optional, Any, AsyncIterator, Sequence, Iterator

from pydantic import BaseModel, Field, validator, root_validator


# Enums for better type safety
class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"


class ContentType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    IMAGE_URL = "image_url"
    FILE = "file"  # ⭐ 新增：文件引用（正确的类型名）


# Enhanced message models
class MessageContent(BaseModel):
    type: ContentType
    text: Optional[str] = None
    image_url: Optional[str] = None
    image_base64: Optional[str] = None
    file_id: Optional[str] = None  # ⭐ 新增：文件ID（用于file_reference）


class LLMMessage(BaseModel):
    role: MessageRole
    content: Union[str, List[MessageContent]]
    name: Optional[str] = Field(None, description="Optional name for the message sender")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


# Standardized response model
# ⭐ 扩展：添加 function_call 支持
class LLMResponse(BaseModel):
    content: Optional[str] = None  # ⭐ 改为 Optional（function call时可能为空）
    usage: Optional[Dict[str, int]] = Field(None, description="Token usage information")
    model: Optional[str] = None
    finish_reason: Optional[str] = None
    function_call: Optional[Dict[str, Any]] = Field(None, description="Function call information")  # ⭐ 新增
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


# Error handling
class LLMClientError(Exception):
    """Base exception for LLM client errors"""
    pass


class RateLimitError(LLMClientError):
    """Rate limit exceeded"""
    pass


class AuthenticationError(LLMClientError):
    """Authentication failed"""
    pass


class InvalidRequestError(LLMClientError):
    """Invalid request parameters"""
    pass


class ModelNotAvailableError(LLMClientError):
    """Model is not available or doesn't exist"""
    pass


# Configuration management
class LLMClientConfig(BaseModel):
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    timeout: int = 300
    max_retries: int = 3
    retry_delay: float = 1.0
    extra_headers: Optional[Dict[str, str]] = None


class BaseModelClient(ABC):
    """
    Base class for all language model clients.
    Enforces a standard interface for building messages and querying models.

    ⭐ 扩展：添加 Function Calling 支持
    """

    def __init__(
        self,
        name: str,
        model_name: str,
        config: Optional[LLMClientConfig] = None,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize the model client with a name and model identifier.
        Args:
            name: Human-readable name for the client
            model_name: Identifier for the specific model being used
            config: Optional configuration for the client
            logger: Optional logger instance
        """
        self.name = name
        self.model_name = model_name
        self.config = config or LLMClientConfig()
        self.logger = logger or logging.getLogger(f"{__name__}.{name}")

        # Monitoring metrics with thread safety
        self._metrics_lock = threading.Lock()
        self._request_count = 0
        self._total_tokens = 0
        self._total_cost = 0.0

    def get_model_name(self) -> str:
        """
        Get the model name.
        """
        return self.model_name

    def build_messages(
        self,
        role: str,
        text: Optional[str] = None,
        image: Optional[str] = None,
        messages: Optional[Sequence[LLMMessage]] = None,
        **kwargs: Any
    ) -> List[LLMMessage]:
        """
        Build messages for API format.

        Args:
            role: Role of the message sender (e.g., "system", "user", "assistant")
            text: Optional text content for the message
            image: Optional image content (base64 encoded)
            messages: Existing messages to include in the conversation context
            **kwargs: Additional parameters for message construction

        Returns:
            A list of LLMMessage objects formatted for the model
        """
        result_messages = []

        # Add existing messages
        if messages:
            result_messages.extend(messages)

        # Create new message
        if text or image:
            content_parts = []

            if text:
                content_parts.append(MessageContent(
                    type=ContentType.TEXT,
                    text=text
                ))

            if image:
                # Assume image is base64 encoded
                content_parts.append(MessageContent(
                    type=ContentType.IMAGE,
                    image_base64=image
                ))

            # For single text content, use string format for optimization
            if len(content_parts) == 1 and content_parts[0].type == ContentType.TEXT:
                content = content_parts[0].text
            else:
                content = content_parts

            message = LLMMessage(
                role=MessageRole(role),
                content=content
            )
            result_messages.append(message)

        return result_messages

    @abstractmethod
    async def aquery(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        functions: Optional[List[Dict]] = None,  # ⭐ 新增：function calling
        function_call: Optional[Union[str, Dict]] = "auto",  # ⭐ 新增
        **kwargs: Any
    ) -> LLMResponse:
        """
        Send an asynchronous query to the language model and return the response.

        ⭐ 扩展：添加 functions 和 function_call 参数支持

        Args:
            messages: List of LLMMessage objects representing the conversation
            temperature: Sampling temperature for response variability
            max_tokens: Maximum number of tokens to generate in the response
            functions: List of function definitions for function calling (optional)
            function_call: Controls which function to call ("auto", "none", or {"name": "function_name"})
            **kwargs: Additional parameters specific to the model client
        Returns:
            The model's response as LLMResponse
        """
        pass

    async def call_with_image(
        self,
        text_prompt: str,
        image_path: str,
        response_format: str = "json",
        max_tokens: int = 1000
    ) -> Dict[str, Any]:
        """
        调用多模态大模型，同时传入文本和图片

        Args:
            text_prompt: 文本提示
            image_path: 图片文件路径
            response_format: 响应格式 ("json" 或 "text")
            max_tokens: 最大 token 数

        Returns:
            模型响应结果
        """
        import base64
        import json

        try:
            # 读取并编码图片
            with open(image_path, "rb") as image_file:
                image_data = base64.b64encode(image_file.read()).decode()

            # 构建消息
            messages = [
                LLMMessage(
                    role=MessageRole.USER,
                    content=[
                        MessageContent(
                            type=ContentType.TEXT,
                            text=text_prompt
                        ),
                        MessageContent(
                            type=ContentType.IMAGE,
                            image_base64=image_data
                        )
                    ]
                )
            ]

            # 调用客户端
            response = await self.aquery(
                messages=messages,
                temperature=0.0,
                max_tokens=max_tokens
            )

            # 处理响应格式
            if response_format == "json":
                try:
                    # 尝试解析为 JSON
                    result = json.loads(response.content)
                    return result
                except json.JSONDecodeError:
                    # 如果不是有效 JSON，包装为 JSON 格式
                    return {"text": response.content}
            else:
                return {"text": response.content}

        except Exception as e:
            self.logger.error(f"{self.model_name} API 调用失败: {str(e)}")
            # 返回错误信息
            if response_format == "json":
                return {"error": str(e), "text": "API调用失败"}
            else:
                return {"text": f"API调用失败: {str(e)}"}

    @abstractmethod
    def calculate_cost(self, usage: Dict[str, int]) -> float:
        """
        Calculate the cost based on token usage.
        This should be implemented by specific clients based on their pricing model.

        Args:
            usage: Dictionary containing token usage (e.g., prompt_tokens, completion_tokens)

        Returns:
            The calculated cost in dollars
        """
        pass

    def format_error(self, error: Exception) -> LLMClientError:
        """
        Convert raw exceptions to standardized LLMClientError types.
        """
        error_message = str(error)

        if "rate limit" in error_message.lower():
            return RateLimitError(error_message)
        elif "authentication" in error_message.lower() or "api key" in error_message.lower():
            return AuthenticationError(error_message)
        elif "invalid" in error_message.lower():
            return InvalidRequestError(error_message)
        elif "model" in error_message.lower() and "not found" in error_message.lower():
            return ModelNotAvailableError(error_message)
        else:
            return LLMClientError(error_message)

    async def close(self):
        """
        Close any open connections or resources.
        Should be implemented by specific clients if needed.
        """
        pass

    # Monitoring methods
    def update_metrics(self, tokens: int, cost: float) -> None:
        """
        Thread-safe update of usage metrics.

        Args:
            tokens: Number of tokens used in the request
            cost: Cost of the request in dollars
        """
        with self._metrics_lock:
            self._request_count += 1
            self._total_tokens += tokens
            self._total_cost += cost

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get usage metrics for this client (thread-safe).
        """
        with self._metrics_lock:
            return {
                "request_count": self._request_count,
                "total_tokens": self._total_tokens,
                "total_cost": self._total_cost,
                "model": self.model_name
            }

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name} model={self.model_name}>"