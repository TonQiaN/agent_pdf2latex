"""
Client Manager for import_v2
简化版本，专注于 import_v2 的需求
"""
from typing import Optional
from .openai_client import OpenAIClient
from .google_client import GoogleClient
from .xai_client import XaiClient
from .base import BaseModelClient


class ClientManager:
    """
    Client Manager for import_v2
    提供不同场景下的客户端创建方法
    """

    @classmethod
    def create_classifier_client(cls) -> BaseModelClient:
        """
        创建分类器客户端
        用于判断试卷类型（Type1 or Type2）

        模型：GPT-5（统一使用 GPT-5）
        场景：分析前3页文本，判断试卷类型
        """
        return OpenAIClient(model_name="gpt-5")

    @classmethod
    def create_agent_client(cls, model: str = "gpt-5") -> BaseModelClient:
        """
        创建主Agent客户端
        用于处理单道题目（纯视觉 + Function Calling）

        模型：GPT-5（支持图片 + Function Calling）
        场景：逐题处理，调用function获取页面图片
        """
        return OpenAIClient(model_name=model)

    @classmethod
    def create_metadata_client(cls) -> BaseModelClient:
        """
        创建元数据提取客户端
        用于提取题目的 topic, subtopic, difficulty

        模型：GPT-5（统一使用 GPT-5）
        场景：后处理阶段，批量提取元数据
        """
        return OpenAIClient(model_name="gpt-5")

    @classmethod
    def create_vision_validator_client(cls) -> BaseModelClient:
        """
        创建图片验证客户端
        用于 verify_image_crop() - 验证图片裁剪

        模型：GPT-5（支持 Vision + 统一使用 GPT-5）
        场景：Agent调用，验证图片边界是否正确
        """
        return OpenAIClient(model_name="gpt-5")

    @classmethod
    def create_latex_validator_client(cls) -> BaseModelClient:
        """
        创建LaTeX验证客户端
        用于 LaTeX 错误分析和修复建议

        模型：GPT-5（统一使用 GPT-5）
        场景：compile_latex失败时，分析错误并提供修复建议
        """
        return OpenAIClient(model_name="gpt-5")

    @classmethod
    def get_all_clients(cls) -> dict:
        """
        获取所有预定义客户端
        用于测试或批量初始化

        Returns:
            {
                "classifier": BaseModelClient,
                "agent": BaseModelClient,
                "metadata": BaseModelClient,
                "vision_validator": BaseModelClient,
                "latex_validator": BaseModelClient
            }
        """
        return {
            "classifier": cls.create_classifier_client(),
            "agent": cls.create_agent_client(),
            "metadata": cls.create_metadata_client(),
            "vision_validator": cls.create_vision_validator_client(),
            "latex_validator": cls.create_latex_validator_client(),
        }