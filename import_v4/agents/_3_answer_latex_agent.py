"""Answer LaTeX Generator Agent"""

import json
import time
from typing import List, Tuple, Optional, TYPE_CHECKING
from loguru import logger
from agents import Usage

if TYPE_CHECKING:
    from . import UsageWithDuration

from ..config.settings import settings
from ..models.schemas import AnswerLatexOutput, ImageInfo
from ..clients.client_manager import ClientManager
from ..clients.base import LLMMessage, MessageContent, MessageRole, ContentType


def get_answer_latex_prompt(question_label: str, solution_pages: List[int], question_index: int) -> str:
    """生成答案 LaTeX 提示词"""
    
    pages_str = ", ".join(map(str, solution_pages))
    
    return f"""You are a professional LaTeX converter for exam answers/solutions.

=== Your Task ===
Convert the answer for question **{question_label}** from the solution PDF to clean, compilable LaTeX code.

=== Answer Location ===
- Question Label: {question_label}
- Solution Pages: [{pages_str}] (0-based page indexing)
- **Note**: These page numbers are for reference. The actual answer content may appear on nearby pages or span across adjacent pages.

=== Conversion Guidelines ===

1. **Read Solution Content**:
   - The answer is expected around page(s) {pages_str}
   - Check nearby pages if the solution spans multiple pages or starts/ends on adjacent pages
   - Read ALL working and steps
   - Include complete solution process

2. **Convert to LaTeX**:
   - Show all working steps clearly
   - Use \\begin{{align*}}...\\end{{align*}} for multi-step calculations
   - Use \\therefore, \\implies for logical connections
   - Highlight final answer with \\boxed{{}} or \\textbf{{Answer:}}
   - Include text explanations between steps

3. **Extract Marks**:
   - Look for marks indicators: "[3 marks]", "(2m)", "3m", etc.
   - Extract the numerical value

4. **Handle Images**:
   - Note any solution diagrams or graphs
   - Use placeholder: \\includegraphics[width=0.5\\textwidth]{{Figures/idPLACEHOLDER{question_index}_sol_1.png}}
   - For multiple images, use: Figures/idPLACEHOLDER{question_index}_sol_1.png, Figures/idPLACEHOLDER{question_index}_sol_2.png, etc.
   - For each image, record:
     * page_number: which page the image appears on (0-based)
     * bbox: bounding box [x1, y1, x2, y2] (origin at top-left corner)
     * description: brief description of the image

5. **Formatting Rules**:
   - **MUST start with: \\item** (do NOT include the question label)
   - **For answers with sub-parts (i), (ii), (iii), MUST use \\begin{{enumerate}}[label=(\\roman*)] and \\item for each sub-part**
   - Clear step-by-step presentation
   - Use \\text{{}} for English within math mode
   - Show intermediate steps
   - Emphasize final answer

=== Output Format ===
Return ONLY valid JSON:
{{
    "question_label": "{question_label}",
    "answer_latex": "...complete LaTeX solution...",
    "answer_images": [
        {{
            "page_number": 0,
            "bbox": [100.5, 200.3, 400.7, 500.2],
            "description": "Solution diagram showing triangles"
        }}
    ],
    "marks": 3,
    "compilation_success": true,
    "error_message": null
}}

=== Examples ===

Example 1 (without images):
{{
    "question_label": "10(a)",
    "answer_latex": "\\\\item \\\\begin{{align*}}\\nx^2 + 3x - 4 &= 0 \\\\\\\\\\n(x + 4)(x - 1) &= 0 \\\\\\\\\\nx &= -4 \\\\text{{ or }} x = 1\\n\\\\end{{align*}}\\n\\\\textbf{{Answer:}} $x = -4$ or $x = 1$",
    "answer_images": [],
    "marks": 2,
    "compilation_success": true,
    "error_message": null
}}

Example 2 (with images):
{{
    "question_label": "Question 5",
    "answer_latex": "\\\\item \\\\includegraphics[width=0.5\\\\textwidth]{{Figures/idPLACEHOLDER5_sol_1.png}}\\n\\\\begin{{align*}}\\nArea &= \\\\frac{{1}}{{2}} \\\\times base \\\\times height \\\\\\\\\\n&= \\\\frac{{1}}{{2}} \\\\times 4 \\\\times 3 \\\\\\\\\\n&= 6 \\\\text{{ cm}}^2\\n\\\\end{{align*}}",
    "answer_images": [
        {{
            "page_number": 35,
            "bbox": [50.0, 100.0, 300.0, 350.0],
            "description": "Diagram showing triangle with labeled sides"
        }}
    ],
    "marks": 3,
    "compilation_success": true,
    "error_message": null
}}

Example 3 (with sub-parts - MUST use this format):
{{
    "question_label": "Question 12",
    "answer_latex": "\\\\item\\n\\\\begin{{enumerate}}[label=(\\\\roman*)]\\n\\\\item\\n\\\\begin{{align*}}\\n\\\\int_0^k \\\\frac{{x}}{{1+x^2}} \\\\, dx &= 1\\\\\\\\\\n\\\\frac{{1}}{{2}}\\\\left[\\\\ln(1+x^2)\\\\right]_0^k &= 1\\\\\\\\\\n\\\\ln(1+k^2) - \\\\ln(1) &= 2\\\\\\\\\\n1+k^2 &= e^2\\\\\\\\\\nk &= \\\\sqrt{{e^2 - 1}}, \\\\quad k > 0\\n\\\\end{{align*}}\\n\\\\item\\n\\\\begin{{align*}}\\nf'(x) &= \\\\frac{{(1+x^2)(1-x(2x))}}{{(1+x^2)^2}} \\\\\\\\\\n\\\\quad \\\\quad \\\\quad &= \\\\quad \\\\frac{{1-x^2}}{{(1+x^2)^2}}\\\\\\\\\\nf'(x) &= 0 \\\\quad \\\\implies \\\\quad 1-x^2 = 0 \\\\\\\\\\nx &= \\\\pm 1 \\\\\\\\\\n\\\\therefore \\\\quad x&=1 \\\\quad \\\\text{{is mode}} \\\\quad (x \\\\geq 0)\\n\\\\end{{align*}}\\n\\\\item\\n\\\\begin{{align*}}\\nF(x) &= \\\\frac{{1}}{{2}} \\\\ln(1 + x^2), \\\\ \\\\text{{from (i)}} \\\\\\\\\\nP(1 \\\\leq x \\\\leq 2) &= F(2) - F(1) \\\\\\\\\\n&= \\\\frac{{1}}{{2}} \\\\ln(5) - \\\\frac{{1}}{{2}} \\\\ln(2) \\\\\\\\\\n&= \\\\frac{{1}}{{2}} \\\\ln\\\\left(\\\\frac{{5}}{{2}}\\\\right) \\\\\\\\\\n&= 0.4581\\n\\\\end{{align*}}\\n\\\\end{{enumerate}}",
    "answer_images": [],
    "marks": 8,
    "compilation_success": true,
    "error_message": null
}}

Now convert the answer.
"""


async def generate_answer_latex_direct(
    question_label: str,
    solution_pages: List[int],
    solution_file_id: str,
    question_index: Optional[int] = None
) -> Tuple[AnswerLatexOutput, "UsageWithDuration"]:
    """
    生成单道题目答案的 LaTeX 代码
    
    Args:
        question_label: 题目标签
        solution_pages: 答案所在页码列表（0-based）
        solution_file_id: 已上传的 solution 文件 ID
        question_index: 题目索引（可选，用于生成图片占位符）
    
    Returns:
        Tuple[AnswerLatexOutput, UsageWithDuration]: (LaTeX输出, API使用统计含时间)
    """
    from . import UsageWithDuration
    
    # 记录开始时间
    start_time = time.time()
    
    # 如果 question_index 为 None，尝试从 question_label 提取数字，否则使用默认值 0
    if question_index is None:
        import re
        # 尝试从 label 中提取数字（如 "Question 6" -> 6, "10(a)" -> 10）
        match = re.search(r'\d+', question_label)
        question_index = int(match.group()) if match else 0
    
    client = ClientManager.create_agent_client()
    
    logger.info(f"[A] 📝 Generating LaTeX for answer {question_label} (index: {question_index})")
    logger.info(f"[A]    Pages: {solution_pages}, File: {solution_file_id}")
    
    # 构建 prompt
    system_prompt = get_answer_latex_prompt(question_label, solution_pages, question_index)
    
    # 构建消息
    user_content = [
        MessageContent(
            type=ContentType.TEXT,
            text=f"Convert answer for {question_label} to LaTeX. Return JSON."
        ),
        MessageContent(
            type=ContentType.FILE,
            file_id=solution_file_id
        )
    ]
    
    messages = [
        LLMMessage(role=MessageRole.SYSTEM, content=system_prompt),
        LLMMessage(role=MessageRole.USER, content=user_content)
    ]
    
    # 调用 API（带重试机制）
    max_retries = 2
    current_max_tokens = 8000
    
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
                logger.error(f"[A] Empty response content for {question_label}")
                logger.error(f"[A] Response object: {response}")
                logger.error(f"[A] finish_reason: {response.finish_reason}")
                logger.error(f"[A] usage: {response.usage}")
                
                # 如果是因为长度限制且还有重试机会
                if response.finish_reason == 'length' and retry < max_retries - 1:
                    current_max_tokens = int(current_max_tokens * 1.5)  # 增加 50%
                    logger.warning(f"[A] Response truncated. Retrying with max_tokens={current_max_tokens}")
                    continue
                else:
                    raise ValueError(
                        f"API returned empty content. finish_reason={response.finish_reason}, "
                        f"tokens={response.usage.get('completion_tokens', 0) if response.usage else 0}"
                    )
            
            # 解析响应
            response_data = json.loads(response.content)
            
            # 构造输出对象
            latex_output = AnswerLatexOutput(**response_data)
            
            # 构造 Usage
            usage = Usage()
            if response.usage:
                usage.requests = 1
                usage.input_tokens = response.usage.get("prompt_tokens", 0)
                usage.output_tokens = response.usage.get("completion_tokens", 0)
                usage.total_tokens = response.usage.get("total_tokens", 0)
            
            # 计算耗时
            duration = time.time() - start_time
            
            logger.info(f"[A] ✓ Generated LaTeX for answer {question_label}")
            logger.info(f"[A]    LaTeX length: {len(latex_output.answer_latex)} chars")
            logger.info(f"[A]    Marks: {latex_output.marks}")
            logger.info(f"[A]    Duration: {duration:.2f}s")
            logger.info(f"[A]    Usage: {usage.total_tokens} tokens")
            
            # 返回带时间的 usage
            usage_with_duration = UsageWithDuration(usage=usage, duration_seconds=duration)
            return latex_output, usage_with_duration
            
        except json.JSONDecodeError as e:
            logger.error(f"[A] Failed to parse JSON (attempt {retry + 1}/{max_retries}): {e}")
            logger.error(f"[A] Response: {response.content[:500] if response.content else '(empty)'}")
            
            # 如果还有重试机会且疑似长度问题
            if retry < max_retries - 1:
                current_max_tokens = int(current_max_tokens * 1.5)
                logger.warning(f"[A] Retrying with max_tokens={current_max_tokens}")
                continue
            else:
                raise
        except Exception as e:
            logger.error(f"Failed to generate answer LaTeX for {question_label}: {e}")
            raise

