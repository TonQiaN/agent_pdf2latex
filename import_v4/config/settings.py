"""Configuration settings for import_v4"""

import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings"""
    
    # OpenAI配置
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-5"  # 默认模型（最新的 gpt-4o）
    
    # Agent配置
    max_turns_per_question: int = 15
    max_latex_fix_attempts: int = 2
    
    # 文件上传配置
    file_upload_purpose: str = "assistants"
    auto_cleanup_files: bool = False  # 是否自动清理上传的文件
    
    # 分类器配置
    classifier_max_turns: int = 5
    classification_sample_pages: int = 3  # 用于分类的页面数量（取倒数第2、4、6页，或最后3页）
    
    # PDF 渲染配置
    pdf_render_quality: str = "medium"  # low (1.0x), medium (1.5x), high (2.0x)
    
    # Lister配置
    lister_max_turns: int = 10
    
    # 输出配置
    output_dir: str = "output"
    save_question_list: bool = True  # 是否保存题目清单
    
    class Config:
        env_file = ".env"
        env_prefix = "EXAM_PROCESSOR_"
    
    def model_post_init(self, __context) -> None:
        """初始化后处理：尝试从多个来源获取 API key"""
        if not self.openai_api_key:
            # 尝试从环境变量获取（不带前缀）
            self.openai_api_key = os.getenv("OPENAI_API_KEY")
        
        if not self.openai_api_key:
            # 尝试从环境变量获取（带前缀）
            self.openai_api_key = os.getenv("EXAM_PROCESSOR_OPENAI_API_KEY")
        
        # 如果还是没有，给出友好的错误提示
        if not self.openai_api_key:
            raise ValueError(
                "OpenAI API Key 未配置！\n"
                "请通过以下任一方式设置：\n"
                "1. 环境变量：export OPENAI_API_KEY=your-api-key\n"
                "2. 环境变量：export EXAM_PROCESSOR_OPENAI_API_KEY=your-api-key\n"
                "3. .env 文件：EXAM_PROCESSOR_OPENAI_API_KEY=your-api-key\n"
                "4. .env 文件：OPENAI_API_KEY=your-api-key"
            )


settings = Settings()

