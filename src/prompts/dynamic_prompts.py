"""
Dynamic Prompts for PDF to LaTeX Workflow
Using LangChain 1.0 @dynamic_prompt decorator to access ModelRequest context
"""

from langchain.agents.middleware.types import ModelRequest, dynamic_prompt

# ============================================================================
# Dynamic Prompt Functions
# ============================================================================

@dynamic_prompt
def build_dynamic_system_prompt(request: ModelRequest) -> str:
    """
    根据 PDFWorkflowContext 动态构建 system prompt
    使用 request.runtime.context 访问 PDFWorkflowContext

    当前支持步骤：
    - Step 0: classify - 分类试卷类型
    - Step 1: lister - 列出所有题目
    """
    step = request.runtime.context.step 

    # 根据步骤选择对应的 prompt 构建函数
    if step == "classify":
        prompt = _build_classify_prompt()
        print(prompt)
        return prompt

    elif step == "lister":
        prompt = _build_lister_prompt(
            exam_type=request.runtime.context.exam_type,
        )
        print(prompt)
        return prompt

    else:
        return f"You are a helpful assistant for step: {step}"


# ============================================================================
# Prompt Building Functions
# ============================================================================

def _build_classify_prompt() -> str:
    """构建分类器 prompt"""
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

                **Important**: Base your decision on multiple indicators, not just one feature."""


def _build_lister_prompt(exam_type: str) -> str:
    """
    构建列题器 prompt
    
    暂时删除了 emphasize 参数，简化重试逻辑
    
    Args:
        exam_type: "type1" 或 "type2"
        emphasize: 是否强调规则（用于重试）
    """
    
    # Type1 规则
    type1_rules = """【Type1 Rules】(Separate Answer Booklet):
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
                        11(a)       ← Question 4: "11(a)" """
    
    # Type2 规则
    type2_rules = """【Type2 Rules】(Answer on Paper):
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
                            (a)          ← Sub-part of Question 12, NOT separate"""
    
    # 选择规则
    cutting_rules = type1_rules if exam_type == "type1" else type2_rules
    
    # 强调文本（用于重试）
    emphasis = ""
    # if emphasize:
    if exam_type == "type1":
        emphasis = """
                    ⚠️ **CRITICAL REMINDER for Type1**:
                    - You MUST split questions to the (a), (b), (c) level
                    - DO NOT list "Question 10" or "Question 11" as single questions
                    - EVERY question label should contain (a), (b), (c), etc.
                    - Example: If you see "10(a)", "10(b)", "10(c)", list them as THREE separate questions
                    - Pattern to follow: "10(a)", "10(b)", "10(c)", "11(a)", "11(b)", etc.
                    - This is a Type1 exam with SEPARATE answer booklet - questions are split into sub-parts!"""
    else:  # type2
        emphasis = """
                    ⚠️ **CRITICAL REMINDER for Type2**:
                    - You MUST NOT split (a), (b), (c) into separate questions
                    - DO NOT list "10(a)", "10(b)" as separate questions
                    - List ONLY "Question N" format (e.g., "Question 1", "Question 2")
                    - If a question has sub-parts (a), (b), (c), they are ALL part of ONE question
                    - Example: "Question 11" with (a), (b), (c) below = ONE question labeled "Question 11"
                    - This is a Type2 exam - answers are written ON the paper, sub-parts are NOT separate!"""

    return f"""You are a Question Lister Agent. Your task is to scan the entire paper PDF and create a **complete, accurate list** of all questions.

                === Exam Type ===
                {exam_type}

                === Question Splitting Rules ===
                {cutting_rules}
                {emphasis}

                === Your Task ===
                1. Systematically scan the entire paper PDF
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

                === Quality Check ===
                Before returning, verify:
                1. total_questions == len(questions)
                2. question_index are sequential (1, 2, 3, ...)
                3. No duplicate question_labels
                4. All question_labels follow the format rules

                Begin scanning now using the file_search tool. Be thorough and accurate!"""


# ============================================================================
# Export
# ============================================================================

__all__ = [
    "build_dynamic_system_prompt",
]

