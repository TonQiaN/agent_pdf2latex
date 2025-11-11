"""Question Labelling Agent - Label questions with topic, subtopic, type, difficulty, and mark"""

import json
import time
from typing import List, Optional, Tuple, TYPE_CHECKING
from loguru import logger
from agents import Usage

if TYPE_CHECKING:
    from . import UsageWithDuration

from ..config.settings import settings
from ..models.schemas import QuestionLabelOutput, ImageInfo
from ..clients.client_manager import ClientManager
from ..clients.base import LLMMessage, MessageContent, MessageRole, ContentType
from ....management.topic_operations import get_all_subtopics


def get_labelling_prompt(
    question_index: int,
    question_label: str,
    question_latex: str,
    answer_latex: Optional[str],
    subtopics_list: List[dict],
    existing_mark: Optional[int] = None
) -> str:
    """
    生成题目标注的提示词
    
    Args:
        question_index: 题目索引（顺序号）
        question_label: 题目标签
        question_latex: 题目 LaTeX 代码
        answer_latex: 答案 LaTeX 代码（可选）
        subtopics_list: 可用的 subtopic 列表
        existing_mark: 已有的分数（可选）
    
    Returns:
        Prompt string
    """
    # 构建 subtopic 选项列表
    # 统一字段名处理：支持 topicid/topic_id 和 topicname/topic_name 两种格式
    subtopics_text = "\n".join([
        f"  {idx + 1}. Topic: {s.get('topic_name') or s.get('topicname', 'N/A')} (topic_id: {s.get('topicid') or s.get('topic_id', 'N/A')}) | "
        f"Subtopic: {s.get('subtopic_name') or s.get('subtopicname', 'N/A')} (subtopic_id: {s.get('subtopicid') or s.get('subtopic_id', 'N/A')})"
        for idx, s in enumerate(subtopics_list)
    ])
    
    mark_instruction = ""
    if existing_mark is not None:
        mark_instruction = f"\n- **Mark**: The question already has a mark of {existing_mark}. Verify if this is correct based on the question content. If incorrect, extract the correct mark."
    else:
        mark_instruction = "\n- **Mark**: Extract the mark from the question (look for notations like [5], [8 marks], etc.). If not found, leave as null."
    
    answer_section = ""
    if answer_latex:
        answer_section = f"""
=== Answer Content ===
{answer_latex}

**Note**: The answer content can help you understand the question better and determine its difficulty.
"""
    
    return f"""You are a Question Labelling Agent. Your task is to analyze a question and label it with accurate metadata.

=== Question Information ===
Question Index: {question_index}
Question Label: {question_label}

=== Question Content ===
{question_latex}
{answer_section}
=== Your Task ===

You need to label this question with the following metadata:

1. **Topic and Subtopic** (MOST IMPORTANT):
   - You MUST select the MOST ACCURATE subtopic from the provided list below
   - You CANNOT create new topics or subtopics - you MUST choose from the list
   - The subtopic_id is the MOST CRITICAL field - it must be accurate
   - Provide a confidence score (0.0-1.0) for your subtopic selection
   - If you are uncertain, explain why in the reasoning field

2. **Question Type** (REQUIRED):
   - You MUST choose EXACTLY ONE from: "short answer" OR "multiple choice"
   - **Multiple Choice**: Has explicit options (A, B, C, D, etc.), usually with instructions like "circle", "select", "choose"
   - **Short Answer**: Requires students to write their answer, may have blank lines, underscores, or answer spaces
   - Look at the question structure and answer format to determine the type

3. **Difficulty** (OPTIONAL):
   - Assess the difficulty based on:
     * Complexity of concepts involved
     * Number of steps required to solve
     * Level of mathematical reasoning needed
   - Common values: "Easy", "Medium", "Hard", or specific difficulty levels
   - If uncertain, you can leave it as null

4. **Mark** (OPTIONAL):{mark_instruction}

=== Available Topics and Subtopics ===

You MUST select from this list (DO NOT create new ones):

{subtopics_text}

**CRITICAL RULES**:
- You MUST select a subtopic_id from the list above
- The subtopic_id is the MOST IMPORTANT field - accuracy is critical
- If no subtopic matches perfectly, choose the CLOSEST match and explain in reasoning
- Provide confidence score for your subtopic selection

=== Output Format ===

Return ONLY valid JSON (no markdown, no code blocks):
{{
    "question_index": {question_index},
    "question_label": "{question_label}",
    "topic_id": <integer>,
    "subtopic_id": <integer>,
    "question_type": "short answer" or "multiple choice",
    "difficulty": "<string>" or null,
    "mark": <integer> or null,
    "confidence": <float between 0.0 and 1.0>,
    "reasoning": "<detailed explanation of your decisions, especially for subtopic selection>"
}}

=== Examples ===

Example 1 (Multiple Choice):
{{
    "question_index": 3,
    "question_label": "Question 3",
    "topic_id": 15,
    "subtopic_id": 42,
    "question_type": "multiple choice",
    "difficulty": "Medium",
    "mark": 2,
    "confidence": 0.95,
    "reasoning": "This is a multiple choice question about derivatives. The subtopic 'Derivatives of Trigonometric Functions' (subtopic_id: 42) is the most accurate match. The question has 4 options (A, B, C, D) and asks to select the correct answer."
}}

Example 2 (Short Answer):
{{
    "question_index": 10,
    "question_label": "10(a)",
    "topic_id": 12,
    "subtopic_id": 28,
    "question_type": "short answer",
    "difficulty": "Hard",
    "mark": 5,
    "confidence": 0.88,
    "reasoning": "This is a short answer question about quadratic equations. The subtopic 'Solving Quadratic Equations' (subtopic_id: 28) matches well. The question requires students to show their working and write the answer. The difficulty is high because it involves completing the square method."
}}

Now analyze the question and provide the labels.
"""


async def label_question_direct(
    question_index: int,
    question_label: str,
    question_latex: str,
    answer_latex: Optional[str] = None,
    question_images: Optional[List[ImageInfo]] = None,
    subject_id: int = None,
    grade_id: int = None,
    existing_mark: Optional[int] = None
) -> Tuple[QuestionLabelOutput, "UsageWithDuration"]:
    """
    标注题目（直接 API 调用）
    
    Args:
        question_index: 题目索引（顺序号，1-based）
        question_label: 题目标签（如 "10(a)", "Question 21"）
        question_latex: 题目 LaTeX 代码
        answer_latex: 答案 LaTeX 代码（可选）
        question_images: 题目中的图片列表（可选）
        subject_id: Subject ID（必需，用于获取可用的 subtopics）
        grade_id: Grade ID（必需，用于获取可用的 subtopics）
        existing_mark: 已有的分数（可选，如果已提取）
    
    Returns:
        Tuple[QuestionLabelOutput, UsageWithDuration]: (标注输出, API使用统计含时间)
    """
    from . import UsageWithDuration
    
    if subject_id is None or grade_id is None:
        raise ValueError("subject_id and grade_id are required to get available subtopics")
    
    # 记录开始时间
    start_time = time.time()
    
    # 获取可用的 subtopics
    logger.info(f"[Label] 📋 Fetching available subtopics for subject_id={subject_id}, grade_id={grade_id}")
    subtopics = await get_all_subtopics(
        subject_id=subject_id,
        grade_id=grade_id
    )
    
    if not subtopics:
        raise ValueError(f"No subtopics found for subject_id={subject_id}, grade_id={grade_id}")
    
    logger.info(f"[Label] ✓ Found {len(subtopics)} available subtopics")
    
    # 创建客户端
    client = ClientManager.create_agent_client()
    
    logger.info(f"[Label] 🏷️  Labelling question {question_label}")
    
    # 构建 prompt
    system_prompt = get_labelling_prompt(
        question_index=question_index,
        question_label=question_label,
        question_latex=question_latex,
        answer_latex=answer_latex,
        subtopics_list=subtopics,
        existing_mark=existing_mark
    )
    
    # 构建用户消息
    user_content = [
        MessageContent(
            type=ContentType.TEXT,
            text=f"Analyze and label question {question_label}. Return JSON."
        )
    ]
    
    # 如果有图片，添加图片内容（如果图片有 base64 数据）
    if question_images:
        for img in question_images:
            # 检查是否有 image_base64 属性（可能在某些情况下不存在）
            if hasattr(img, 'image_base64') and img.image_base64:
                user_content.append(
                    MessageContent(
                        type=ContentType.IMAGE,
                        image_base64=img.image_base64
                    )
                )
    
    messages = [
        LLMMessage(role=MessageRole.SYSTEM, content=system_prompt),
        LLMMessage(role=MessageRole.USER, content=user_content)
    ]
    
    # 调用 API（带重试机制）
    max_retries = 2
    current_max_tokens = 3000
    
    for retry in range(max_retries):
        try:
            response = await client.aquery(
                messages=messages,
                temperature=0.0,
                max_tokens=current_max_tokens,
                response_format={"type": "json_object"}
            )
            
            # 检查响应内容
            if not response.content:
                logger.error(f"[Label] Empty response content for Q{question_index}")
                logger.error(f"[Label] Response object: {response}")
                logger.error(f"[Label] finish_reason: {response.finish_reason}")
                logger.error(f"[Label] usage: {response.usage}")
                
                # 如果是因为长度限制且还有重试机会
                if response.finish_reason == 'length' and retry < max_retries - 1:
                    current_max_tokens = int(current_max_tokens * 1.5)
                    logger.warning(f"[Label] Response truncated. Retrying with max_tokens={current_max_tokens}")
                    continue
                else:
                    raise ValueError(
                        f"API returned empty content. finish_reason={response.finish_reason}, "
                        f"tokens={response.usage.get('completion_tokens', 0) if response.usage else 0}"
                    )
            
            # 解析响应
            response_data = json.loads(response.content)
            
            # 验证 question_type
            question_type = response_data.get("question_type", "").lower()
            if question_type not in ["short answer", "multiple choice"]:
                logger.warning(f"[Label] ⚠️  Invalid question_type: {question_type}, defaulting to 'short answer'")
                question_type = "short answer"
            
            # 构造输出对象
            label_output = QuestionLabelOutput(
                question_index=response_data.get("question_index", question_index),
                question_label=response_data.get("question_label", question_label),
                topic_id=response_data.get("topic_id"),
                subtopic_id=response_data.get("subtopic_id"),
                question_type=question_type,
                difficulty=response_data.get("difficulty"),
                mark=response_data.get("mark", existing_mark),
                confidence=response_data.get("confidence"),
                reasoning=response_data.get("reasoning", "")
            )
            
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
            logger.info(f"[Label] ✓ Labelled question {question_index}: {question_label}")
            logger.info(f"[Label]    Topic ID: {label_output.topic_id}, Subtopic ID: {label_output.subtopic_id}")
            logger.info(f"[Label]    Type: {label_output.question_type}, Difficulty: {label_output.difficulty}")
            logger.info(f"[Label]    Mark: {label_output.mark}, Confidence: {label_output.confidence}")
            logger.info(f"[Label]    Duration: {duration:.2f}s")
            logger.info(f"[Label]    API Usage: {usage.input_tokens} input + {usage.output_tokens} output = {usage.total_tokens} tokens")
            
            # 返回带时间的 usage
            usage_with_duration = UsageWithDuration(usage=usage, duration_seconds=duration)
            return label_output, usage_with_duration
            
        except json.JSONDecodeError as e:
            logger.error(f"[Label] Failed to parse JSON (attempt {retry + 1}/{max_retries}): {e}")
            logger.error(f"[Label] Response: {response.content[:500] if response.content else '(empty)'}")
            
            # 如果还有重试机会
            if retry < max_retries - 1:
                current_max_tokens = int(current_max_tokens * 1.5)
                logger.warning(f"[Label] Retrying with max_tokens={current_max_tokens}")
                continue
            else:
                raise
        except Exception as e:
            logger.error(f"[Label] ❌ Failed to label question {question_label}: {e}")
            raise

