"""Question Lister Agent - List all questions from paper PDF"""

import asyncio
import json
import re
import time
from typing import List, Tuple, TYPE_CHECKING
from loguru import logger
from agents import Usage

if TYPE_CHECKING:
    from . import UsageWithDuration

from ..config.settings import settings
from ..models.schemas import QuestionList, QuestionItem
from ..utils.usage_tracker import PRICING
from ..clients.client_manager import ClientManager
from ..clients.base import LLMMessage, MessageContent, MessageRole, ContentType


def calculate_cost(usage: Usage, model: str = None) -> float:
    """
    计算 API 调用成本（参考 usage_tracker.py）
    
    Args:
        usage: Usage 对象
        model: 模型名称（默认使用 settings 中配置的模型）
    
    Returns:
        成本（美元）
    """
    if model is None:
        model = settings.openai_model
    
    # 获取定价
    pricing = PRICING.get(model, PRICING.get("gpt-5", {"input": 1.25, "output": 10.0}))
    
    # 分别计算 input 和 output 成本
    input_cost = (usage.input_tokens / 1_000_000) * pricing["input"]
    output_cost = (usage.output_tokens / 1_000_000) * pricing["output"]
    
    return input_cost + output_cost


def validate_question_list_format(question_list: QuestionList, exam_type: str) -> Tuple[bool, str]:
    """
    验证题目列表格式是否符合试卷类型
    
    Args:
        question_list: 题目清单
        exam_type: 试卷类型 ("type1" or "type2")
    
    Returns:
        Tuple[bool, str]: (是否有效, 错误原因)
    """
    labels = [q.question_label for q in question_list.questions]
    
    # Type1: 应该包含 (a), (b), (c) 等小题格式
    # 格式: 10(a), 11(b), 12(c)
    type1_pattern = re.compile(r'^\d+\([a-z]\)$', re.IGNORECASE)
    
    # Type2: 应该是纯 "Question N" 格式，不应该有小题
    # 格式: Question 1, Question 10, Question 21
    type2_pattern = re.compile(r'^Question\s+\d+$', re.IGNORECASE)
    
    if exam_type == "type1":
        # Type1 验证：至少要有一些 X(a), X(b) 格式的题目
        type1_count = sum(1 for label in labels if type1_pattern.match(label))
        
        if type1_count == 0:
            return False, (
                f"Type1 exam should contain questions like '10(a)', '11(b)', but found none. "
                f"Sample labels: {labels[:5]}"
            )
        
        # 如果少于 20% 的题目符合 type1 格式，也认为有问题
        if len(labels) > 0 and type1_count / len(labels) < 0.2:
            return False, (
                f"Type1 exam should have most questions in 'X(a)' format, "
                f"but only {type1_count}/{len(labels)} ({type1_count/len(labels)*100:.1f}%) match. "
                f"Sample labels: {labels[:5]}"
            )
        
        return True, ""
    
    elif exam_type == "type2":
        # Type2 验证：不应该有 X(a), X(b) 这样的独立题目
        type1_count = sum(1 for label in labels if type1_pattern.match(label))
        
        if type1_count > 0:
            # 找出所有 type1 格式的题目
            type1_labels = [label for label in labels if type1_pattern.match(label)]
            return False, (
                f"Type2 exam should NOT have questions like '10(a)', '11(b)' as separate questions, "
                f"but found {type1_count}: {type1_labels[:5]}"
            )
        
        return True, ""
    
    return True, ""


def get_question_lister_prompt(exam_type: str, emphasize: bool = False) -> str:
    """
    生成Question Lister的prompt
    
    Args:
        exam_type: "type1" or "type2"
        emphasize: 是否强调关键规则（重试时使用）
    
    Returns:
        Prompt string
    """
    if exam_type == "type1":
        cutting_rule = """
【Type1 Rules】(Separate Answer Booklet):
- Question 10 is a **section title**, not an independent question
- 10(a), 10(b), 10(c) are **independent questions** (minimum splitting unit)
- 10(c)(i), 10(c)(ii) are **sub-parts** of 10(c), NOT separate questions
- Recognition pattern: ^\\d+\\([a-z]\\)$ indicates start of independent question

Example:
  10          ← Section title, NOT a question
  10(a)       ← Question 1: "10(a)"
  10(b)       ← Question 2: "10(b)"
  10(c)       ← Question 3: "10(c)"
    (i)       ← Sub-part of 10(c), NOT separate
    (ii)      ← Sub-part of 10(c), NOT separate
  11(a)       ← Question 4: "11(a)"
"""
        
        emphasis = ""
        if emphasize:
            emphasis = """

⚠️ **CRITICAL REMINDER for Type1**:
- You MUST split questions to the (a), (b), (c) level
- DO NOT list "Question 10" or "Question 11" as single questions
- EVERY question label should contain (a), (b), (c), etc.
- Example: If you see "10(a)", "10(b)", "10(c)", list them as THREE separate questions
- Pattern to follow: "10(a)", "10(b)", "10(c)", "11(a)", "11(b)", etc.
- This is a Type1 exam with SEPARATE answer booklet - questions are split into sub-parts!
"""
    
    else:  # type2
        cutting_rule = """
【Type2 Rules】(Answer on Paper):
- Each "Question N" (where N is a number) is **one complete question** (minimum splitting unit)
- Sub-parts like (a), (b), (c) are NOT separate questions
- Recognition pattern: ^Question \\d+$ indicates start of question
- **IMPORTANT**: Include ALL questions from Question 1 onwards (including short/multiple-choice questions at the beginning)

Example:
  Question 1     ← Question 1: "Question 1" (may be a short/multiple-choice question)
  Question 2     ← Question 2: "Question 2"
  ...
  Question 11    ← Question 11: "Question 11" (may have sub-parts below)
    (a)          ← Sub-part of Question 11, NOT separate
    (b)          ← Sub-part of Question 11, NOT separate
  Question 12    ← Question 12: "Question 12"
    (a)          ← Sub-part of Question 12, NOT separate
"""
        
        emphasis = ""
        if emphasize:
            emphasis = """

⚠️ **CRITICAL REMINDER for Type2**:
- You MUST NOT split (a), (b), (c) into separate questions
- DO NOT list "10(a)", "10(b)" as separate questions
- List ONLY "Question N" format (e.g., "Question 1", "Question 2")
- If a question has sub-parts (a), (b), (c), they are ALL part of ONE question
- Example: "Question 11" with (a), (b), (c) below = ONE question labeled "Question 11"
- This is a Type2 exam - answers are written ON the paper, sub-parts are NOT separate!
"""
    
    return f"""You are a Question Lister Agent. Your task is to scan the entire paper PDF and create a **complete, accurate list** of all questions.

=== Exam Type ===
{exam_type}

=== Question Splitting Rules ===
{cutting_rule}
{emphasis}

=== Your Task ===
1. Use the file_search tool to systematically scan the entire paper PDF
2. Identify ALL questions in the document (from Question 1 to the last question)
3. For each question, record:
   - question_index: Sequential number starting from 1 (1, 2, 3, ...)
   - question_label: **Exact label** as it appears in the paper (e.g., "10(a)", "Question 1", "Question 21")

=== Search Strategy ===
- **Start from Question 1** (or the first question in the document)
- Search for ALL question patterns systematically (don't skip short/multiple-choice questions at the beginning)
- Scan through the entire document from beginning to end
- Verify you've reached the last question
- Double-check the count and ensure Question 1 is included

=== Critical Rules ===
✅ DO:
- Follow the splitting rules **strictly**
- **Start from Question 1** - don't skip early questions
- Include ALL questions: short questions, multiple-choice questions, AND longer questions with sub-parts
- Preserve exact question labels (including parentheses, capitalization)
- Number questions sequentially (1, 2, 3, ...)
- Include ALL questions, no matter how short

❌ DON'T:
- Skip the first few questions (e.g., Question 1-10)
- Split sub-parts into separate questions
- Guess or skip questions
- Change the question labels
- Include section titles as questions (for type1)

=== Output Format ===
**IMPORTANT: Return your response as a JSON object** with the following structure:
{{
    "exam_type": "{exam_type}",
    "total_questions": <count>,
    "questions": [
        {{"question_index": 1, "question_label": "..."}},
        {{"question_index": 2, "question_label": "..."}},
        ...
    ]
}}

=== Quality Check ===
Before returning, verify:
1. total_questions == len(questions)
2. question_index are sequential (1, 2, 3, ...)
3. No duplicate question_labels
4. All question_labels follow the format rules

Begin scanning now using the file_search tool. Be thorough and accurate!
"""


async def list_all_questions_direct(
    exam_type: str,
    paper_file_id: str,  # 直接使用 file_id（通过 files.create 上传）
    retry_count: int = 0  # 新增参数：重试次数
) -> Tuple[QuestionList, "UsageWithDuration"]:
    """
    使用 Chat Completions API 直接调用（不使用 agents 框架）
    使用 file 类型传递文件
    
    Args:
        exam_type: 试卷类型 ("type1" or "type2")
        paper_file_id: 已上传的 paper 文件 ID (通过 files.create 获取)
        retry_count: 当前重试次数（内部使用）
    
    Returns:
        Tuple[QuestionList, UsageWithDuration]: (题目清单, API使用统计含时间)
    """
    from . import UsageWithDuration
    
    # 记录开始时间
    start_time = time.time()
    
    # 创建客户端
    client = ClientManager.create_agent_client()
    
    emphasize = retry_count > 0  # 重试时强调规则
    
    logger.info(f"📋 Listing all questions from paper (Direct API)...")
    logger.info(f"   Exam type: {exam_type}")
    logger.info(f"   Paper file ID: {paper_file_id}")
    if emphasize:
        logger.info(f"   ⚠️  Retry attempt {retry_count} - Emphasizing splitting rules")
    
    # 构建系统提示（重试时强调规则）
    system_prompt = get_question_lister_prompt(exam_type, emphasize=emphasize)
    
    # 构建用户消息（包含文件引用）
    user_content = [
        MessageContent(
            type=ContentType.TEXT,
            text="List all questions from the paper PDF. Be systematic and thorough. Return your response as JSON."
        ),
        MessageContent(
            type=ContentType.FILE,
            file_id=paper_file_id  # ⭐ 使用 file 类型
        )
    ]
    
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
            max_tokens=4000,  # Question list 可能较长
            response_format={"type": "json_object"}
        )
        
        # 解析 JSON 响应
        response_data = json.loads(response.content)
        
        # 构造 QuestionList 对象
        question_list = QuestionList(**response_data)
        
        # 手动构造 Usage 对象
        usage = Usage()
        if response.usage:
            usage.requests = 1
            usage.input_tokens = response.usage.get("prompt_tokens", 0)
            usage.output_tokens = response.usage.get("completion_tokens", 0)
            usage.total_tokens = response.usage.get("total_tokens", 0)
        
        # 验证一致性
        if not question_list.validate_consistency():
            logger.warning(
                f"⚠️  Inconsistency detected (Direct API): total_questions={question_list.total_questions}, "
                f"actual count={len(question_list.questions)}"
            )
        
        # 输出日志
        logger.info(f"✓ Found {question_list.total_questions} questions (Direct API)")
        logger.info(f"   API Usage: {usage.input_tokens} input + {usage.output_tokens} output = {usage.total_tokens} tokens")
        
        # 显示前几道题
        preview_count = min(5, len(question_list.questions))
        logger.info(f"   Sample labels: {[q.question_label for q in question_list.questions[:preview_count]]}")
        for q in question_list.questions[:preview_count]:
            logger.info(f"  [{q.question_index}] {q.question_label}")
        
        if question_list.total_questions > preview_count:
            logger.info(f"  ... and {question_list.total_questions - preview_count} more")
        
        # ✨ 新增：验证题目格式
        is_valid, error_reason = validate_question_list_format(question_list, exam_type)
        
        if not is_valid:
            logger.warning(f"⚠️  Question list validation failed!")
            logger.warning(f"   Reason: {error_reason}")
            
            # 如果还没有重试过，则重试一次
            if retry_count == 0:
                logger.info(f"🔄 Retrying with emphasized rules...")
                return await list_all_questions_direct(
                    exam_type=exam_type,
                    paper_file_id=paper_file_id,
                    retry_count=retry_count + 1
                )
            else:
                # 已经重试过一次，记录警告但继续（避免无限循环）
                logger.error(
                    f"❌ Validation failed after retry. Proceeding with potentially incorrect results.\n"
                    f"   Reason: {error_reason}"
                )
        else:
            logger.info(f"✓ Question list format validated successfully for {exam_type}")
        
        # 计算耗时
        duration = time.time() - start_time
        logger.info(f"   Duration: {duration:.2f}s")
        
        # 返回带时间的 usage
        usage_with_duration = UsageWithDuration(usage=usage, duration_seconds=duration)
        return question_list, usage_with_duration
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        logger.error(f"Response content: {response.content}")
        raise
    except Exception as e:
        logger.error(f"Failed to list questions (Direct API): {e}")
        raise


async def list_all_questions_with_pages_direct(
    exam_type: str,
    paper_pdf_path: str,
    solution_pdf_path: str
) -> Tuple['QuestionListWithPages', Usage, dict]:
    """
    三步法标注页码（避免 32MB 文件大小限制）：
    1. 列出所有题目（使用 list_all_questions_direct）
    2. 标注 paper 页码（单独上传 paper PDF）
    3. 标注 solution 页码（单独上传 solution PDF）
    
    Args:
        exam_type: 试卷类型 ("type1" or "type2")
        paper_pdf_path: Paper PDF 路径
        solution_pdf_path: Solution PDF 路径
    
    Returns:
        Tuple[QuestionListWithPages, Usage, dict]: (题目清单含页码, 总API使用统计, 分步统计)
    """
    from ..models.schemas import QuestionListWithPages, QuestionItemWithPages
    
    logger.info(f"📋 Listing questions with page locations (3-Step Method)...")
    logger.info(f"   Exam type: {exam_type}")
    
    total_usage = Usage()
    
    # Step 1: List all questions (using existing lister with paper PDF only)
    logger.info("\n" + "="*80)
    logger.info("Step 1/3: Listing all questions...")
    logger.info("="*80)
    
    # Upload paper PDF for Step 1
    import tempfile
    from pathlib import Path
    from openai import AsyncOpenAI
    from ..config.settings import settings
    
    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    with open(paper_pdf_path, 'rb') as f:
        paper_file_temp = await openai_client.files.create(file=f, purpose="assistants")
    logger.info(f"  Uploaded temp paper file: {paper_file_temp.id}")
    
    try:
        question_list, step1_usage = await list_all_questions_direct(
            exam_type=exam_type,
            paper_file_id=paper_file_temp.id
        )
        # step1_usage is UsageWithDuration, extract the Usage object
        total_usage.add(step1_usage.usage)
        
        logger.info(f"✓ Step 1 complete - Found {question_list.total_questions} questions")
        
    finally:
        await openai_client.files.delete(paper_file_temp.id)
        logger.info("  Cleaned up temp paper file")
    
    # Step 2 & 3: Annotate pages in parallel
    logger.info("\n" + "="*80)
    logger.info("Step 2&3/3: Annotating paper and solution pages (parallel)...")
    logger.info("="*80)
    
    # 并发执行
    logger.info("  → Starting parallel execution...")
    try:
        results = await asyncio.gather(
            annotate_paper_pages(question_list, paper_pdf_path),
            annotate_solution_pages(question_list, solution_pdf_path),
            return_exceptions=True  # 捕获异常而不是立即失败
        )
        
        # 检查每个任务的结果
        errors = []
        if isinstance(results[0], Exception):
            errors.append(f"Paper annotation failed: {results[0]}")
        if isinstance(results[1], Exception):
            errors.append(f"Solution annotation failed: {results[1]}")
        
        if errors:
            error_msg = "; ".join(errors)
            logger.error(f"❌ Parallel execution failed: {error_msg}")
            raise RuntimeError(error_msg)
        
        # 解包结果
        (paper_pages_map, step2_usage), (solution_pages_map, step3_usage) = results
        
        # 累加usage
        total_usage.add(step2_usage)
        total_usage.add(step3_usage)
        
        logger.info(f"✓ Step 2&3 complete (parallel execution)")
        
    except Exception as e:
        logger.error(f"❌ Unexpected error in parallel execution: {e}")
        raise
    
    # Merge results
    logger.info("\n" + "="*80)
    logger.info("Merging results...")
    logger.info("="*80)
    
    questions_with_pages = []
    for q in question_list.questions:
        questions_with_pages.append(
            QuestionItemWithPages(
                question_index=q.question_index,
                question_label=q.question_label,
                paper_pages=paper_pages_map.get(q.question_label, []),
                solution_pages=solution_pages_map.get(q.question_label, [])
            )
        )
    
    result = QuestionListWithPages(
        exam_type=question_list.exam_type,
        total_questions=len(questions_with_pages),
        questions=questions_with_pages
    )
    
    # 验证
    if not result.validate_consistency():
        logger.warning(
            f"⚠️  Inconsistency: total_questions={result.total_questions}, "
            f"actual count={len(result.questions)}"
        )
    
    # 构建 usage breakdown（使用正确的模型定价）
    usage_breakdown = {
        "step1_list_questions": {
            "input_tokens": step1_usage.input_tokens,
            "output_tokens": step1_usage.output_tokens,
            "total_tokens": step1_usage.total_tokens,
            "estimated_cost_usd": round(calculate_cost(step1_usage.usage), 4)
        },
        "step2_annotate_paper_pages": {
            "input_tokens": step2_usage.input_tokens,
            "output_tokens": step2_usage.output_tokens,
            "total_tokens": step2_usage.total_tokens,
            "estimated_cost_usd": round(calculate_cost(step2_usage), 4)
        },
        "step3_annotate_solution_pages": {
            "input_tokens": step3_usage.input_tokens,
            "output_tokens": step3_usage.output_tokens,
            "total_tokens": step3_usage.total_tokens,
            "estimated_cost_usd": round(calculate_cost(step3_usage), 4)
        }
    }
    
    # 日志输出（使用正确的成本计算）
    total_cost = calculate_cost(total_usage)
    logger.info(f"\n✓ All steps complete - Found {result.total_questions} questions with page locations")
    logger.info(f"   Total API Usage: {total_usage.input_tokens} input + {total_usage.output_tokens} output = {total_usage.total_tokens} tokens")
    logger.info(f"   Estimated Cost: ${total_cost:.4f} (Model: {settings.openai_model})")
    
    # 显示每步的usage（使用正确的成本计算）
    logger.info(f"\n   📋 Usage Breakdown:")
    logger.info(f"      Step 1 (List Questions):      {step1_usage.total_tokens:>6,} tokens (${calculate_cost(step1_usage.usage):.4f})")
    logger.info(f"      Step 2&3 (Parallel Annotation):")
    logger.info(f"        → Paper Pages:              {step2_usage.total_tokens:>6,} tokens (${calculate_cost(step2_usage):.4f})")
    logger.info(f"        → Solution Pages:           {step3_usage.total_tokens:>6,} tokens (${calculate_cost(step3_usage):.4f})")
    
    # 显示示例
    preview_count = min(3, len(result.questions))
    logger.info(f"\n📋 Sample results (showing {preview_count} of {result.total_questions}):")
    for q in result.questions[:preview_count]:
        paper_pages_str = ', '.join(map(str, q.paper_pages))
        solution_pages_str = ', '.join(map(str, q.solution_pages))
        logger.info(
            f"  [{q.question_index}] {q.question_label} "
            f"(paper: [{paper_pages_str}], solution: [{solution_pages_str}])"
        )
    
    if result.total_questions > preview_count:
        logger.info(f"  ... and {result.total_questions - preview_count} more")
    
    return result, total_usage, usage_breakdown


async def annotate_paper_pages(
    question_list: QuestionList,
    paper_pdf_path: str
) -> Tuple[dict, Usage]:
    """
    为已有的题目清单标注 paper 页码
    
    Args:
        question_list: 已有的题目清单
        paper_pdf_path: Paper PDF 路径
    
    Returns:
        Tuple[Dict[question_label -> paper_pages], Usage]
        例如: ({"10(a)": [5, 6], "10(b)": [7]}, usage)
    """
    import tempfile
    from pathlib import Path
    from openai import AsyncOpenAI
    from ..preprocessing.pdf_renderer import add_page_markers_to_pdf
    
    logger.info("[Step 2/Paper] 📄 Annotating paper pages...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Add page markers
        marked_paper_path = Path(temp_dir) / "paper_marked.pdf"
        add_page_markers_to_pdf(paper_pdf_path, str(marked_paper_path), zero_based=True)
        
        # Upload marked PDF
        from ..config.settings import settings
        openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
        
        with open(marked_paper_path, 'rb') as f:
            paper_file = await openai_client.files.create(file=f, purpose="assistants")
        logger.info(f"[Step 2/Paper]   Uploaded paper: {paper_file.id}")
        
        try:
            # Build prompt
            questions_str = "\n".join([
                f"{q.question_index}. {q.question_label}"
                for q in question_list.questions
            ])
            
            system_prompt = f"""You are analyzing a paper PDF with page markers.

The PDF has visible PAGE_INDEX_N markers (0-based) at the top-right of each page.

Here are the questions in this paper:
{questions_str}

For EACH question, identify ALL pages where it appears (may span multiple pages).

Return JSON:
{{
    "annotations": [
        {{"question_label": "10(a)", "paper_pages": [5]}},
        {{"question_label": "10(b)", "paper_pages": [6, 7]}},
        ...
    ]
}}

CRITICAL:
- paper_pages is ALWAYS an array, even for single-page questions
- Page indices are 0-based
- Include ALL pages if question spans multiple pages
- Return annotations for ALL {len(question_list.questions)} questions
"""
            
            client = ClientManager.create_agent_client()
            
            messages = [
                LLMMessage(role=MessageRole.SYSTEM, content=system_prompt),
                LLMMessage(
                    role=MessageRole.USER,
                    content=[
                        MessageContent(type=ContentType.TEXT, text="Annotate pages for all questions. Return JSON."),
                        MessageContent(type=ContentType.FILE, file_id=paper_file.id)
                    ]
                )
            ]
            
            response = await client.aquery(
                messages=messages,
                temperature=0.0,
                max_tokens=16000,  # 增加限制以支持更多题目
                response_format={"type": "json_object"}
            )
            
            # 检查响应是否为空
            if not response.content or not response.content.strip():
                logger.error(f"❌ Empty response from API (Paper Pages)!")
                logger.error(f"   Usage: {response.usage}")
                logger.error(f"   This may indicate the response was truncated due to token limits.")
                raise ValueError(
                    f"API returned empty response for paper pages annotation. "
                    f"Completion tokens: {response.usage.get('completion_tokens', 0)}, "
                    f"Max allowed: 16000. "
                    f"The response may have been truncated."
                )
            
            result = json.loads(response.content)
            
            # 调试：显示 API 返回的原始结构
            logger.debug(f"   API returned {len(result.get('annotations', []))} annotations")
            if result.get('annotations'):
                first_few = result['annotations'][:3]
                last_few = result['annotations'][-3:] if len(result['annotations']) > 3 else []
                logger.debug(f"   First annotations: {[a.get('question_label') for a in first_few]}")
                if last_few:
                    logger.debug(f"   Last annotations: {[a.get('question_label') for a in last_few]}")
            
            # Convert to dict
            paper_pages_map = {
                item["question_label"]: item["paper_pages"]
                for item in result["annotations"]
            }
            
            # Create Usage object
            usage = Usage()
            if response.usage:
                usage.requests = 1
                usage.input_tokens = response.usage.get("prompt_tokens", 0)
                usage.output_tokens = response.usage.get("completion_tokens", 0)
                usage.total_tokens = response.usage.get("total_tokens", 0)
            
            logger.info(f"[Step 2/Paper] ✓ Annotated {len(paper_pages_map)} questions with paper pages")
            logger.info(f"[Step 2/Paper]   API Usage: {usage.input_tokens} input + {usage.output_tokens} output = {usage.total_tokens} tokens")
            
            # 调试：检查是否所有题目都被标注
            expected_labels = {q.question_label for q in question_list.questions}
            annotated_labels = set(paper_pages_map.keys())
            missing_labels = expected_labels - annotated_labels
            
            if missing_labels:
                logger.warning(f"[Step 2/Paper] ⚠️  {len(missing_labels)} questions missing paper page annotations!")
                logger.warning(f"[Step 2/Paper]   Missing labels: {sorted(missing_labels)[:10]}")  # 显示前10个
                logger.warning(f"[Step 2/Paper]   Expected {len(expected_labels)} labels, got {len(annotated_labels)} annotations")
            
            return paper_pages_map, usage
            
        finally:
            await openai_client.files.delete(paper_file.id)
            logger.info("[Step 2/Paper]   Cleaned up paper file")


async def annotate_solution_pages(
    question_list: QuestionList,
    solution_pdf_path: str
) -> Tuple[dict, Usage]:
    """
    为已有的题目清单标注 solution 页码
    
    Args:
        question_list: 已有的题目清单
        solution_pdf_path: Solution PDF 路径
    
    Returns:
        Tuple[Dict[question_label -> solution_pages], Usage]
        例如: ({"10(a)": [2], "10(b)": [3, 4]}, usage)
    """
    import tempfile
    from pathlib import Path
    from openai import AsyncOpenAI
    from ..preprocessing.pdf_renderer import add_page_markers_to_pdf
    
    logger.info("[Step 3/Solution] 📄 Annotating solution pages...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Add page markers
        marked_solution_path = Path(temp_dir) / "solution_marked.pdf"
        add_page_markers_to_pdf(solution_pdf_path, str(marked_solution_path), zero_based=True)
        
        # Upload marked PDF
        from ..config.settings import settings
        openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
        
        with open(marked_solution_path, 'rb') as f:
            solution_file = await openai_client.files.create(file=f, purpose="assistants")
        logger.info(f"[Step 3/Solution]   Uploaded solution: {solution_file.id}")
        
        try:
            # Build prompt
            questions_str = "\n".join([
                f"{q.question_index}. {q.question_label}"
                for q in question_list.questions
            ])
            
            system_prompt = f"""You are analyzing a solution PDF with page markers.

The PDF has visible PAGE_INDEX_N markers (0-based) at the top-right of each page.

Here are the questions (you need to find their ANSWERS in this solution PDF):
{questions_str}

For EACH question, identify ALL pages where its ANSWER appears (may span multiple pages).

Return JSON:
{{
    "annotations": [
        {{"question_label": "10(a)", "solution_pages": [2]}},
        {{"question_label": "10(b)", "solution_pages": [3, 4]}},
        ...
    ]
}}

CRITICAL:
- solution_pages is ALWAYS an array, even for single-page answers
- Page indices are 0-based
- Include ALL pages if answer spans multiple pages
- Return annotations for ALL {len(question_list.questions)} questions
"""
            
            client = ClientManager.create_agent_client()
            
            messages = [
                LLMMessage(role=MessageRole.SYSTEM, content=system_prompt),
                LLMMessage(
                    role=MessageRole.USER,
                    content=[
                        MessageContent(type=ContentType.TEXT, text="Annotate pages for all answers. Return JSON."),
                        MessageContent(type=ContentType.FILE, file_id=solution_file.id)
                    ]
                )
            ]
            
            response = await client.aquery(
                messages=messages,
                temperature=0.0,
                max_tokens=16000,  # 增加限制以支持更多题目
                response_format={"type": "json_object"}
            )
            
            # 检查响应是否为空
            if not response.content or not response.content.strip():
                logger.error(f"❌ Empty response from API (Solution Pages)!")
                logger.error(f"   Usage: {response.usage}")
                logger.error(f"   This may indicate the response was truncated due to token limits.")
                raise ValueError(
                    f"API returned empty response for solution pages annotation. "
                    f"Completion tokens: {response.usage.get('completion_tokens', 0)}, "
                    f"Max allowed: 16000. "
                    f"The response may have been truncated."
                )
            
            result = json.loads(response.content)
            
            # Convert to dict
            solution_pages_map = {
                item["question_label"]: item["solution_pages"]
                for item in result["annotations"]
            }
            
            # Create Usage object
            usage = Usage()
            if response.usage:
                usage.requests = 1
                usage.input_tokens = response.usage.get("prompt_tokens", 0)
                usage.output_tokens = response.usage.get("completion_tokens", 0)
                usage.total_tokens = response.usage.get("total_tokens", 0)
            
            logger.info(f"[Step 3/Solution] ✓ Annotated {len(solution_pages_map)} questions with solution pages")
            logger.info(f"[Step 3/Solution]   API Usage: {usage.input_tokens} input + {usage.output_tokens} output = {usage.total_tokens} tokens")
            
            # 调试：检查是否所有题目都被标注
            expected_labels = {q.question_label for q in question_list.questions}
            annotated_labels = set(solution_pages_map.keys())
            missing_labels = expected_labels - annotated_labels
            
            if missing_labels:
                logger.warning(f"[Step 3/Solution] ⚠️  {len(missing_labels)} questions missing solution page annotations!")
                logger.warning(f"[Step 3/Solution]   Missing labels: {sorted(missing_labels)[:10]}")  # 显示前10个
                logger.warning(f"[Step 3/Solution]   Expected {len(expected_labels)} labels, got {len(annotated_labels)} annotations")
            
            return solution_pages_map, usage
            
        finally:
            await openai_client.files.delete(solution_file.id)
            logger.info("[Step 3/Solution]   Cleaned up solution file")

