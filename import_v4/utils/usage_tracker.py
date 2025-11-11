"""Usage tracking and cost calculation utilities"""

from typing import Dict, Optional
from dataclasses import dataclass, field
from agents import Usage


# GPT-4o 定价（根据实际情况调整）
PRICING = {
    "gpt-4o": {
        "input": 0.0025,   # $2.50 per 1M tokens
        "output": 0.01,    # $10.00 per 1M tokens
    },
    "gpt-4o-2024-11-20": {
        "input": 0.0025,
        "output": 0.01,
    },
    "gpt-4o-mini": {
        "input": 0.00015,  # $0.15 per 1M tokens
        "output": 0.0006,  # $0.60 per 1M tokens
    },
    "gpt-5": {  # 假设价格
        "input": 1.25,
        "output": 10,
    },
}


@dataclass
class StepUsage:
    """单个步骤的 usage 统计"""
    step_name: str
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    estimated_cost_usd: float = 0.0
    duration_seconds: float = 0.0  # 步骤耗时（秒）
    details: Optional[Dict] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "step_name": self.step_name,
            "requests": self.requests,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cached_tokens": self.cached_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 4),
            "duration_seconds": round(self.duration_seconds, 2),
            "details": self.details
        }


class UsageTracker:
    """追踪整个流程的 API usage"""
    
    def __init__(self, model: str = "gpt-4o"):
        self.model = model
        self.steps: Dict[str, StepUsage] = {}
        self.total_usage = Usage()
    
    def add_step_usage(
        self,
        step_name: str,
        usage: Usage,
        details: Optional[Dict] = None,
        duration_seconds: float = 0.0
    ) -> StepUsage:
        """
        添加一个步骤的 usage
        
        Args:
            step_name: 步骤名称
            usage: Usage 对象
            details: 额外的详细信息
            duration_seconds: 步骤耗时（秒）
        
        Returns:
            StepUsage 对象
        """
        # 计算成本
        cost = self._calculate_cost(usage)
        
        # 创建 StepUsage
        step_usage = StepUsage(
            step_name=step_name,
            requests=usage.requests,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            cached_tokens=usage.input_tokens_details.cached_tokens if hasattr(usage, 'input_tokens_details') else 0,
            reasoning_tokens=usage.output_tokens_details.reasoning_tokens if hasattr(usage, 'output_tokens_details') else 0,
            estimated_cost_usd=cost,
            duration_seconds=duration_seconds,
            details=details or {}
        )
        
        # 保存
        self.steps[step_name] = step_usage
        
        # 累加到总计
        self.total_usage.add(usage)
        
        return step_usage
    
    def _calculate_cost(self, usage: Usage) -> float:
        """
        计算成本
        
        Args:
            usage: Usage 对象
        
        Returns:
            成本（美元）
        """
        # 获取定价
        pricing = PRICING.get(self.model, PRICING["gpt-4o"])
        
        # 计算
        input_cost = (usage.input_tokens / 1_000_000) * pricing["input"]
        output_cost = (usage.output_tokens / 1_000_000) * pricing["output"]
        
        return input_cost + output_cost
    
    def get_summary(self) -> Dict:
        """
        获取汇总统计
        
        Returns:
            包含所有步骤和总计的字典
        """
        # 步骤统计
        steps_summary = {
            step_name: step.to_dict()
            for step_name, step in self.steps.items()
        }
        
        # 总计
        total_cost = self._calculate_cost(self.total_usage)
        total_duration = sum(step.duration_seconds for step in self.steps.values())
        
        total_summary = {
            "requests": self.total_usage.requests,
            "input_tokens": self.total_usage.input_tokens,
            "output_tokens": self.total_usage.output_tokens,
            "total_tokens": self.total_usage.total_tokens,
            "cached_tokens": self.total_usage.input_tokens_details.cached_tokens,
            "reasoning_tokens": self.total_usage.output_tokens_details.reasoning_tokens,
            "estimated_cost_usd": round(total_cost, 4),
            "total_duration_seconds": round(total_duration, 2)
        }
        
        return {
            "model": self.model,
            "steps": steps_summary,
            "total": total_summary,
            "pricing_info": {
                "model": self.model,
                "input_price_per_1m_tokens": PRICING.get(self.model, PRICING["gpt-4o"])["input"],
                "output_price_per_1m_tokens": PRICING.get(self.model, PRICING["gpt-4o"])["output"]
            }
        }


def extract_usage_from_result(result) -> Usage:
    """
    从 RunResult 中提取 usage 信息
    
    Args:
        result: Runner.run() 返回的结果
    
    Returns:
        聚合后的 Usage 对象
    """
    total_usage = Usage()
    
    # 遍历所有响应
    if hasattr(result, 'raw_responses'):
        for response in result.raw_responses:
            if hasattr(response, 'usage'):
                total_usage.add(response.usage)
    
    return total_usage

