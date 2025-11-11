"""Question LaTeX Generator Agent"""

import json
import time
from typing import List, Tuple, Optional, TYPE_CHECKING
from loguru import logger
from agents import Usage

if TYPE_CHECKING:
    from . import UsageWithDuration

from ..config.settings import settings
from ..models.schemas import QuestionLatexOutput, ImageInfo
from ..clients.client_manager import ClientManager
from ..clients.base import LLMMessage, MessageContent, MessageRole, ContentType


def get_question_latex_prompt(question_label: str, paper_pages: List[int], question_index: int) -> str:
    """生成题目 LaTeX 提示词"""
    
    pages_str = ", ".join(map(str, paper_pages))
    
    return f"""You are a professional LaTeX converter for exam questions.

=== Your Task ===
Convert question **{question_label}** from the PDF pages to clean, compilable LaTeX code.

=== Question Location ===
- Question Label: {question_label}
- Paper Pages: [{pages_str}] (0-based page indexing)
- **Note**: These page numbers are for reference. The actual question content may appear on nearby pages or span across adjacent pages.

=== Conversion Guidelines ===

1. **Read Question Content**:
   - The question is expected around page(s) {pages_str}
   - Check nearby pages if the question spans multiple pages or starts/ends on adjacent pages
   - Read ALL content across these pages
   - Include all sub-parts like (i), (ii), (iii) OR multiple choice options like A, B, C, D

2. **Convert to LaTeX**:
   - Use standard math environments: $...$ for inline, \\[...\\] or \\begin{{align*}}...\\end{{align*}} for display
   - Keep structure clear and organized
   - Use \\textbf{{}} for emphasis
   - Convert all mathematical symbols accurately
   - Preserve all formatting (fractions, powers, roots, etc.)
   - **For multiple choice questions (A, B, C, D options), use \\begin{{enumerate}}[label=\\Alph*.] format**

3. **Handle Images/Diagrams**:
   - If you see an image, graph, or diagram, note its position
   - Use placeholder: \\includegraphics[width=0.5\\textwidth]{{Figures/idPLACEHOLDER{question_index}_1.png}}
   - For multiple images, use: Figures/idPLACEHOLDER{question_index}_1.png, Figures/idPLACEHOLDER{question_index}_2.png, etc.
   - For each image, record:
     * page_number: which page the image appears on (0-based)
     * bbox: bounding box [x1, y1, x2, y2] (origin at top-left corner)
     * description: brief description of the image

4. **Formatting Rules**:
   - **MUST start with: \\item** (do NOT include the question label)
   - **For sub-parts (i), (ii), (iii), MUST use \\begin{{enumerate}}[label=(\\roman*)] and \\item**
   - **For multiple choice questions (A, B, C, D), MUST use \\begin{{enumerate}}[label=\\Alph*.] and \\item**
   - Keep consistent spacing
   - Don't add extra section titles

5. **Quality Check**:
   - Verify all math brackets match: (), [], \\{{\\}}
   - Check all LaTeX commands are spelled correctly
   - Ensure completeness - don't miss any part

=== Output Format ===
Return ONLY valid JSON (no markdown, no code blocks):
{{
    "question_label": "{question_label}",
    "question_latex": "...complete LaTeX code...",
    "question_images": [
        {{
            "page_number": 5,
            "bbox": [100.5, 200.3, 400.7, 500.2],
            "description": "Graph showing quadratic function"
        }}
    ],
    "compilation_success": true,
    "error_message": null
}}

=== Examples ===

Example 1 (simple):
{{
    "question_label": "10(a)",
    "question_latex": "\\\\item Solve the equation $x^2 + 3x - 4 = 0$.",
    "question_images": [],
    "compilation_success": true,
    "error_message": null
}}

Example 2 (with sub-parts):
{{
    "question_label": "Question 11",
    "question_latex": "\\\\item Consider the function $f(x) = x^2 - 4x + 3$.\\n\\\\begin{{enumerate}}[label=(\\\\roman*)]\\n\\\\item Find the vertex.\\n\\\\item Sketch the graph.\\n\\\\end{{enumerate}}",
    "question_images": [],
    "compilation_success": true,
    "error_message": null
}}

Example 3 (with images):
{{
    "question_label": "Question 8",
    "question_latex": "\\\\item The diagram shows a triangle ABC.\\n\\\\includegraphics[width=0.5\\\\textwidth]{{Figures/idPLACEHOLDER8_1.png}}\\n\\\\begin{{enumerate}}[label=(\\\\roman*)]\\n\\\\item Calculate the area.\\n\\\\item Find the perimeter.\\n\\\\end{{enumerate}}",
    "question_images": [
        {{
            "page_number": 3,
            "bbox": [150.0, 250.0, 450.0, 500.0],
            "description": "Triangle ABC with sides labeled: AB = 5cm, BC = 4cm, AC = 3cm"
        }}
    ],
    "compilation_success": true,
    "error_message": null
}}

Example 4 (multiple choice - MUST use this format):
{{
    "question_label": "Question 3",
    "question_latex": "\\\\item What is the derivative of $\\\\dfrac{{\\\\sin x}}{{e^x}}$?\\n\\\\begin{{enumerate}}[label=\\\\Alph*.]\\n\\\\item $\\\\dfrac{{\\\\sin x + \\\\cos x}}{{e^x}}$\\n\\\\item $\\\\dfrac{{\\\\sin x - \\\\cos x}}{{e^x}}$\\n\\\\item $-\\\\dfrac{{\\\\sin x + \\\\cos x}}{{e^x}}$\\n\\\\item $\\\\dfrac{{\\\\cos x - \\\\sin x}}{{e^x}}$\\n\\\\end{{enumerate}}",
    "question_images": [],
    "compilation_success": true,
    "error_message": null
}}

Example 5 (short answer with sub-parts - MUST use this format for sub-parts):
{{
    "question_label": "Question 15",
    "question_latex": "\\\\item The standard normal distribution function is given by $\\\\varphi(x) = \\\\dfrac{{1}}{{\\\\sqrt{{2\\\\pi}}}} e^{{-\\\\frac{{1}}{{2}}x^2}}$.\\n\\\\begin{{enumerate}}[label=(\\\\roman*)]\\n\\\\item Write down the equation of the normal distribution function, $f(x)$, for a distribution with mean of 20 and variance of 3.\\n\\\\item Find the value of $f(20)$ and state its graphical significance.\\n\\\\item State the coordinates of the points of inflection of the graph $y=f(x)$ of the distribution.\\n\\\\end{{enumerate}}",
    "question_images": [],
    "compilation_success": true,
    "error_message": null
}}

Now convert the question.
"""


async def generate_question_latex_direct(
    question_label: str,
    paper_pages: List[int],
    paper_file_id: str,
    question_index: Optional[int] = None
) -> Tuple[QuestionLatexOutput, "UsageWithDuration"]:
    """
    生成单道题目的 LaTeX 代码（直接 API 调用）
    
    Args:
        question_label: 题目标签（如 "10(a)", "Question 21"）
        paper_pages: 题目所在页码列表（0-based）
        paper_file_id: 已上传的 paper 文件 ID
        question_index: 题目索引（可选，用于生成图片占位符）
    
    Returns:
        Tuple[QuestionLatexOutput, UsageWithDuration]: (LaTeX输出, API使用统计含时间)
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
    
    logger.info(f"[Q] 📝 Generating LaTeX for question {question_label} (index: {question_index})")
    logger.info(f"[Q]    Pages: {paper_pages}, File: {paper_file_id}")
    
    # 构建 prompt
    system_prompt = get_question_latex_prompt(question_label, paper_pages, question_index)
    
    # 构建消息
    user_content = [
        MessageContent(
            type=ContentType.TEXT,
            text=f"Convert question {question_label} to LaTeX. Return JSON."
        ),
        MessageContent(
            type=ContentType.FILE,
            file_id=paper_file_id
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
                logger.error(f"[Q] Empty response content for {question_label}")
                logger.error(f"[Q] Response object: {response}")
                logger.error(f"[Q] finish_reason: {response.finish_reason}")
                logger.error(f"[Q] usage: {response.usage}")
                
                # 如果是因为长度限制且还有重试机会
                if response.finish_reason == 'length' and retry < max_retries - 1:
                    current_max_tokens = int(current_max_tokens * 1.5)  # 增加 50%
                    logger.warning(f"[Q] Response truncated. Retrying with max_tokens={current_max_tokens}")
                    continue
                else:
                    raise ValueError(
                        f"API returned empty content. finish_reason={response.finish_reason}, "
                        f"tokens={response.usage.get('completion_tokens', 0) if response.usage else 0}"
                    )
            
            # 解析响应
            response_data = json.loads(response.content)
            
            # 构造输出对象
            latex_output = QuestionLatexOutput(**response_data)
            
            # 构造 Usage
            usage = Usage()
            if response.usage:
                usage.requests = 1
                usage.input_tokens = response.usage.get("prompt_tokens", 0)
                usage.output_tokens = response.usage.get("completion_tokens", 0)
                usage.total_tokens = response.usage.get("total_tokens", 0)
            
            # 计算耗时
            duration = time.time() - start_time
            
            logger.info(f"[Q] ✓ Generated LaTeX for {question_label}")
            logger.info(f"[Q]    LaTeX length: {len(latex_output.question_latex)} chars")
            logger.info(f"[Q]    Images: {len(latex_output.question_images)}")
            logger.info(f"[Q]    Duration: {duration:.2f}s")
            logger.info(f"[Q]    Usage: {usage.total_tokens} tokens")
            
            # 返回带时间的 usage
            usage_with_duration = UsageWithDuration(usage=usage, duration_seconds=duration)
            return latex_output, usage_with_duration
            
        except json.JSONDecodeError as e:
            logger.error(f"[Q] Failed to parse JSON (attempt {retry + 1}/{max_retries}): {e}")
            logger.error(f"[Q] Response: {response.content[:500] if response.content else '(empty)'}")
            
            # 如果还有重试机会且疑似长度问题
            if retry < max_retries - 1:
                current_max_tokens = int(current_max_tokens * 1.5)
                logger.warning(f"[Q] Retrying with max_tokens={current_max_tokens}")
                continue
            else:
                raise
        except Exception as e:
            logger.error(f"Failed to generate LaTeX for {question_label}: {e}")
            raise

