"""Exam Type Classifier Agent"""

import json
import time
from typing import Tuple, TYPE_CHECKING
from loguru import logger
from agents import Usage

if TYPE_CHECKING:
    from . import UsageWithDuration

from ..config.settings import settings
from ..models.schemas import ExamTypeOutput
from ..clients.client_manager import ClientManager
from ..clients.base import LLMMessage, MessageContent, MessageRole, ContentType


def get_classifier_prompt() -> str:
    """
    分类器提示词（与 import_v3 一致）
    """
    return """Analyze the provided pages of this exam and determine its type.

**Type1** (Separate Answer Booklet):
- Explicitly states "Use a SEPARATE writing booklet" or similar
- No blank lines or answer spaces under questions
- Questions are densely packed
- Example: "10(a)", "10(b)", "10(c)" are independent questions

**Type2** (Answer on Paper):
- Has blank lines or answer spaces under questions, including:
  * Underscores (______)
  * Dotted lines (..................)
  * Multiple blank lines for writing answers
- Clear answer spaces between questions
- Questions have more spacing
- Example: "Question 21" is one complete question with sub-parts (a), (b), (c)

**Analysis Guidelines**:
1. Look for explicit instructions about where to write answers
2. Check for blank answer spaces or lines
3. Observe question density and spacing
4. Note the question numbering pattern

Return JSON with:
{
    "exam_type": "type1" or "type2",
    "reasoning": "Detailed explanation of classification decision",
    "confidence": 0.0-1.0 (optional)
}

**Important**: Base your decision on multiple indicators, not just one feature.
"""


async def classify_exam_type_direct(classification_data: dict) -> Tuple[str, "UsageWithDuration"]:
    """
    使用 clients 直接调用 API 进行试卷类型分类（不使用 agents 框架）
    
    这是一个替代实现，用于对比测试：
    - 直接使用 OpenAIClient 调用 Vision API
    - 手动构造消息和解析响应
    - 手动构造 Usage 对象
    
    Args:
        classification_data: 预处理数据，包含 selected_pages
    
    Returns:
        Tuple[str, UsageWithDuration]: (试卷类型, API使用统计含时间)
    """
    from . import UsageWithDuration
    
    # 记录开始时间
    start_time = time.time()
    
    # 创建客户端
    client = ClientManager.create_classifier_client()
    
    selected_pages = classification_data["selected_pages"]
    page_numbers = [p["page_number"] for p in selected_pages]
    
    logger.info(f"📊 Classifying exam type using pages (Direct API): {page_numbers}")
    
    # 构建系统提示
    system_prompt = get_classifier_prompt()
    
    # 构建用户消息（包含3张图片）
    user_content = [
        MessageContent(
            type=ContentType.TEXT,
            text="Analyze these pages to determine exam type:"
        )
    ]
    
    # 添加每个页面的图片
    for page in selected_pages:
        user_content.append(
            MessageContent(
                type=ContentType.TEXT,
                text=f"\n\nPage {page['page_number']}:"
            )
        )
        user_content.append(
            MessageContent(
                type=ContentType.IMAGE,
                image_base64=page['image_base64']
            )
        )
    
    # 构建消息列表
    messages = [
        LLMMessage(
            role=MessageRole.SYSTEM,
            content=system_prompt
        ),
        LLMMessage(
            role=MessageRole.USER,
            content=user_content
        )
    ]
    
    # 调用 API（使用 JSON 模式）
    try:
        response = await client.aquery(
            messages=messages,
            temperature=0.0,
            max_tokens=2000,  # 增加限制以确保完整响应（分类任务简单，2000足够）
            response_format={"type": "json_object"}  # JSON 模式
        )
        
        # 检查响应内容
        if not response.content:
            logger.error("Empty response content from API")
            logger.error(f"Response object: {response}")
            logger.error(f"Response finish_reason: {response.finish_reason}")
            logger.error(f"Response usage: {response.usage}")
            
            # 如果是因为长度限制，提供更有用的错误信息
            if response.finish_reason == 'length':
                raise ValueError(
                    f"API response was truncated due to max_tokens limit. "
                    f"Tokens used: {response.usage.get('completion_tokens', 0)}. "
                    f"Consider increasing max_tokens parameter."
                )
            else:
                raise ValueError("API returned empty content. This may be due to a refusal or error.")
        
        # 解析 JSON 响应
        response_data = json.loads(response.content)
        
        # 提取分类结果
        exam_type = response_data.get("exam_type", "type1")
        reasoning = response_data.get("reasoning", "")
        confidence = response_data.get("confidence")
        
        # 手动构造 Usage 对象
        usage = Usage()
        if response.usage:
            usage.requests = 1
            usage.input_tokens = response.usage.get("prompt_tokens", 0)
            usage.output_tokens = response.usage.get("completion_tokens", 0)
            usage.total_tokens = response.usage.get("total_tokens", 0)
        
        # 计算耗时
        duration = time.time() - start_time
        
        # 输出日志
        logger.info(f"✓ Classification result (Direct API): {exam_type}")
        logger.info(f"   Reasoning: {reasoning}")
        if confidence:
            logger.info(f"   Confidence: {confidence:.2f}")
        logger.info(f"   Duration: {duration:.2f}s")
        logger.info(f"   API Usage: {usage.input_tokens} input + {usage.output_tokens} output = {usage.total_tokens} tokens")
        
        # 返回带时间的 usage
        usage_with_duration = UsageWithDuration(usage=usage, duration_seconds=duration)
        return exam_type, usage_with_duration
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        logger.error(f"Response content: {response.content if response.content else '(empty)'}")
        logger.error(f"Response finish_reason: {response.finish_reason if hasattr(response, 'finish_reason') else 'N/A'}")
        logger.error(f"Full response: {response}")
        raise
    except ValueError as e:
        logger.error(f"Invalid response: {e}")
        raise
    except Exception as e:
        logger.error(f"Classification failed: {e}")
        raise

