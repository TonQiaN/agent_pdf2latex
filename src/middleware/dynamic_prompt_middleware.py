"""
Dynamic Prompt Middleware with Retry Logic
LangChain 1.0 style middleware using @dynamic_prompt and wrap_model_call
"""

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from typing import Callable, Awaitable


class DynamicPromptWithRetryMiddleware(AgentMiddleware):
    """
    中间件：动态 prompt 注入 + 重试逻辑 + Token 裁剪 + 工具控制
    
    使用 ModelRequest.runtime.context 访问 PDFWorkflowContext
    """
    
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
    
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """同步版本 - 带重试逻辑"""
        from src.models import PDFWorkflowContext
        
        ctx: PDFWorkflowContext = request.runtime.context
        
        # 重试逻辑
        for attempt in range(self.max_retries):
            try:
                # 1. 动态构建 system prompt (已通过 @dynamic_prompt 装饰器完成)
                # request.system_prompt 已经被 build_dynamic_system_prompt 设置
                
                # 2. Token 裁剪
                if request.system_prompt:
                    token_count = self._estimate_token_count(request.system_prompt)
                    if token_count > ctx.token_budget:
                        request.system_prompt = request.system_prompt[:ctx.token_budget * 4]
                
                # 3. 工具控制
                step_config = ctx.get_step_config()
                if not step_config.get("enable_tools", True):
                    request.tools = []
                
                # 4. 调用模型
                response = handler(request)
                
                # 5. 成功返回
                if attempt > 0:
                    print(f"✅ Retry succeeded on attempt {attempt + 1}/{self.max_retries}")
                
                return response
                
            except Exception as e:
                if attempt == self.max_retries - 1:
                    # 最后一次重试失败，抛出异常
                    print(f"❌ All {self.max_retries} retry attempts failed")
                    raise
                
                # 记录重试
                print(f"⚠️  Retry {attempt + 1}/{self.max_retries} after error: {e}")
                
                # 更新 context 的重试计数
                if hasattr(ctx, 'retry_count'):
                    ctx.retry_count = attempt + 1
    
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """异步版本 - 带重试逻辑"""
        from src.models import PDFWorkflowContext
        
        ctx: PDFWorkflowContext = request.runtime.context
        
        # 重试逻辑
        for attempt in range(self.max_retries):
            try:
                # 1. 动态构建 system prompt (已通过 @dynamic_prompt 装饰器完成)
                # request.system_prompt 已经被 build_dynamic_system_prompt 设置
                
                # 2. Token 裁剪
                if request.system_prompt:
                    token_count = self._estimate_token_count(request.system_prompt)
                    if token_count > ctx.token_budget:
                        request.system_prompt = request.system_prompt[:ctx.token_budget * 4]
                
                # 3. 工具控制
                step_config = ctx.get_step_config()
                if not step_config.get("enable_tools", True):
                    request.tools = []
                
                # 4. 调用模型（异步）
                response = await handler(request)
                
                # 5. 成功返回
                if attempt > 0:
                    print(f"✅ Retry succeeded on attempt {attempt + 1}/{self.max_retries}")
                
                return response
                
            except Exception as e:
                if attempt == self.max_retries - 1:
                    # 最后一次重试失败，抛出异常
                    print(f"❌ All {self.max_retries} retry attempts failed")
                    raise
                
                # 记录重试
                print(f"⚠️  Retry {attempt + 1}/{self.max_retries} after error: {e}")
                
                # 更新 context 的重试计数
                if hasattr(ctx, 'retry_count'):
                    ctx.retry_count = attempt + 1
    
    @staticmethod
    def _estimate_token_count(text: str) -> int:
        """粗略估计 token 数量（1 token ≈ 4 个字符）"""
        return max(1, len(text) // 4)


class TokenBudgetMiddleware(AgentMiddleware):
    """
    简化版中间件：仅处理 Token 裁剪
    可以与 @dynamic_prompt 装饰器组合使用
    """
    
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """同步版本"""
        from src.models import PDFWorkflowContext
        
        ctx: PDFWorkflowContext = request.runtime.context
        
        # Token 裁剪
        if request.system_prompt:
            token_count = len(request.system_prompt) // 4
            if token_count > ctx.token_budget:
                request.system_prompt = request.system_prompt[:ctx.token_budget * 4]
                print(f"⚠️  System prompt truncated to {ctx.token_budget} tokens")
        
        return handler(request)
    
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """异步版本"""
        from src.models import PDFWorkflowContext
        
        ctx: PDFWorkflowContext = request.runtime.context
        
        # Token 裁剪
        if request.system_prompt:
            token_count = len(request.system_prompt) // 4
            if token_count > ctx.token_budget:
                request.system_prompt = request.system_prompt[:ctx.token_budget * 4]
                print(f"⚠️  System prompt truncated to {ctx.token_budget} tokens")
        
        return await handler(request)


class ToolControlMiddleware(AgentMiddleware):
    """
    简化版中间件：仅处理工具控制
    根据 FlowContext.get_step_config() 动态启用/禁用工具
    """
    
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """同步版本"""
        from src.models import PDFWorkflowContext
        
        ctx: PDFWorkflowContext = request.runtime.context
        step_config = ctx.get_step_config()
        
        # 工具控制
        if not step_config.get("enable_tools", True):
            request.tools = []
            print(f"🔧 Tools disabled for step: {ctx.step}")
        elif "available_tools" in step_config:
            # 过滤工具列表（如果配置了白名单）
            available = step_config["available_tools"]
            request.tools = [t for t in request.tools if t.name in available]
            print(f"🔧 Tools filtered to: {available}")
        
        return handler(request)
    
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """异步版本"""
        from src.models import PDFWorkflowContext
        
        ctx: PDFWorkflowContext = request.runtime.context
        step_config = ctx.get_step_config()
        
        # 工具控制
        if not step_config.get("enable_tools", True):
            request.tools = []
            print(f"🔧 Tools disabled for step: {ctx.step}")
        elif "available_tools" in step_config:
            # 过滤工具列表（如果配置了白名单）
            available = step_config["available_tools"]
            request.tools = [t for t in request.tools if t.name in available]
            print(f"🔧 Tools filtered to: {available}")
        
        return await handler(request)


__all__ = [
    "DynamicPromptWithRetryMiddleware",
    "TokenBudgetMiddleware",
    "ToolControlMiddleware",
]

