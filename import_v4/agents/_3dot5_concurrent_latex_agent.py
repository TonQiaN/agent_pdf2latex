"""Concurrent LaTeX Generator Agent

This agent handles concurrent generation of Question and Answer LaTeX,
providing approximately 50% performance improvement over sequential execution.
"""

import asyncio
import time
from typing import Tuple, List, Optional, TYPE_CHECKING
from loguru import logger

if TYPE_CHECKING:
    from . import UsageWithDuration

from ..models.schemas import QuestionLatexOutput, AnswerLatexOutput, QuestionLabelOutput
from ._2_question_latex_agent import generate_question_latex_direct
from ._3_answer_latex_agent import generate_answer_latex_direct
from ._5_labelling_agent import label_question_direct


async def generate_question_and_answer_latex_concurrent(
    question_label: str,
    paper_pages: List[int],
    solution_pages: List[int],
    paper_file_id: str,
    solution_file_id: str,
    question_index: Optional[int] = None,
    subject_id: Optional[int] = None,
    grade_id: Optional[int] = None,
    enable_labelling: bool = True
) -> Tuple[
    QuestionLatexOutput, 
    AnswerLatexOutput, 
    Optional[QuestionLabelOutput],
    "UsageWithDuration", 
    "UsageWithDuration",
    Optional["UsageWithDuration"]
]:
    """
    并发生成单道题目的 question LaTeX、answer LaTeX 和 labelling
    
    相比顺序执行可节省约 50% 的时间。
    
    工作原理:
    - 第一步：使用 asyncio.gather() 并发执行 question 和 answer 生成
    - 第二步：使用生成的 LaTeX 执行 labelling（依赖第一步结果）
    - 自动错误处理和性能统计
    
    Args:
        question_label: 题目标签（如 "10(a)", "Question 21"）
        paper_pages: 题目所在页码列表（0-based）
        solution_pages: 答案所在页码列表（0-based）
        paper_file_id: 已上传的 paper 文件 ID
        solution_file_id: 已上传的 solution 文件 ID
        question_index: 题目索引（可选，用于生成图片占位符）
        subject_id: 学科 ID（可选，用于 labelling）
        grade_id: 年级 ID（可选，用于 labelling）
        enable_labelling: 是否启用 labelling（默认 True）
    
    Returns:
        Tuple[QuestionLatexOutput, AnswerLatexOutput, Optional[QuestionLabelOutput], 
              UsageWithDuration, UsageWithDuration, Optional[UsageWithDuration]]:
            (question_latex, answer_latex, label_output, question_usage, answer_usage, label_usage)
    
    Raises:
        Exception: 如果任一任务失败，会抛出相应异常
    
    Performance:
        - Sequential: Q_time + A_time + L_time ≈ 10-12s
        - Concurrent (Q+A): max(Q_time, A_time) + L_time ≈ 6-8s
        - Time saved: ~40%
    
    Example:
        >>> q_latex, a_latex, label, q_usage, a_usage, l_usage = await generate_question_and_answer_latex_concurrent(
        ...     question_label="Question 6",
        ...     paper_pages=[4],
        ...     solution_pages=[0, 35],
        ...     paper_file_id="file-xxx",
        ...     solution_file_id="file-yyy",
        ...     subject_id=2,
        ...     grade_id=2
        ... )
        >>> print(f"Question LaTeX: {len(q_latex.question_latex)} chars")
        >>> print(f"Answer LaTeX: {len(a_latex.answer_latex)} chars")
        >>> print(f"Topic: {label.topic_id}, Difficulty: {label.difficulty}")
    """
    from . import UsageWithDuration
    
    # 记录开始时间
    start_time = time.time()
    
    logger.info(f"🚀 Starting concurrent LaTeX generation for {question_label}")
    logger.info(f"   Question pages: {paper_pages}")
    logger.info(f"   Answer pages: {solution_pages}")
    
    # 并发执行两个任务
    try:
        results = await asyncio.gather(
            generate_question_latex_direct(
                question_label=question_label,
                paper_pages=paper_pages,
                paper_file_id=paper_file_id,
                question_index=question_index
            ),
            generate_answer_latex_direct(
                question_label=question_label,
                solution_pages=solution_pages,
                solution_file_id=solution_file_id,
                question_index=question_index
            ),
            return_exceptions=True  # 捕获异常而不是立即失败
        )
        
        # 检查结果
        if isinstance(results[0], Exception):
            logger.error(f"❌ Question LaTeX generation failed: {results[0]}")
            raise results[0]
        
        if isinstance(results[1], Exception):
            logger.error(f"❌ Answer LaTeX generation failed: {results[1]}")
            raise results[1]
        
        # 解包结果
        (q_latex, q_usage), (a_latex, a_usage) = results
        
        latex_duration = time.time() - start_time
        logger.info(f"✅ Step 1/2: Concurrent LaTeX generation completed for {question_label}")
        logger.info(f"   LaTeX duration: {latex_duration:.2f}s")
        
        # Step 2: Label question（依赖 LaTeX 结果）
        label_output = None
        label_usage = None
        
        if enable_labelling:
            try:
                logger.info(f"🏷️  Step 2/2: Labelling {question_label}...")
                
                label_output, label_usage = await label_question_direct(
                    question_index=question_index or 0,
                    question_label=question_label,
                    question_latex=q_latex.question_latex,
                    answer_latex=a_latex.answer_latex,
                    question_images=q_latex.question_images,
                    subject_id=subject_id,
                    grade_id=grade_id,
                    existing_mark=a_latex.marks
                )
                
                logger.info(f"✅ Step 2/2: Labelling completed for {question_label}")
                logger.info(f"   Topic: {label_output.topic_id}, Subtopic: {label_output.subtopic_id}")
                logger.info(f"   Type: {label_output.question_type}, Difficulty: {label_output.difficulty}")
                
            except Exception as e:
                logger.error(f"❌ Labelling failed for {question_label}: {e}")
                logger.warning(f"⚠️  Continuing without labelling data")
                # 不抛出异常，允许继续（labelling 失败不应阻止整个流程）
        
        # 计算总耗时
        total_duration = time.time() - start_time
        
        # 计算性能提升
        sequential_duration = q_usage.duration_seconds + a_usage.duration_seconds
        if label_usage:
            sequential_duration += label_usage.duration_seconds
        
        time_saved = sequential_duration - total_duration
        percentage_saved = (time_saved / sequential_duration * 100) if sequential_duration > 0 else 0
        
        # 日志输出
        logger.info(f"✅ Complete workflow finished for {question_label}")
        logger.info(f"   Total duration: {total_duration:.2f}s (vs {sequential_duration:.2f}s sequential)")
        logger.info(f"   Time saved: {time_saved:.2f}s ({percentage_saved:.1f}%)")
        total_tokens = q_usage.total_tokens + a_usage.total_tokens
        if label_usage:
            total_tokens += label_usage.total_tokens
        logger.info(f"   Total tokens: {total_tokens:,}")
        
        return q_latex, a_latex, label_output, q_usage, a_usage, label_usage
        
    except Exception as e:
        logger.error(f"❌ Concurrent LaTeX generation failed for {question_label}: {e}")
        raise

