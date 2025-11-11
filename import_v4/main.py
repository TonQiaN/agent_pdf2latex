"""Main entry point for import_v4 - delegates to workflow"""

from typing import Optional
from .workflow import run_file_based_workflow_to_lister


async def process_exam_to_lister(
    paper_pdf_path: str,
    solution_pdf_path: str,
    exam_id: Optional[str] = None,
    output_dir: Optional[str] = None
) -> dict:
    """
    V4 File-Based Workflow 主入口（仅到 Lister 阶段）
    
    这是一个简化版本，用于测试和验证前几个步骤。
    
    Args:
        paper_pdf_path: Paper PDF路径
        solution_pdf_path: Solution PDF路径
        exam_id: 试卷ID（可选，默认使用时间戳）
        output_dir: 输出目录（可选）
    
    Returns:
        包含处理结果的字典
    """
    return await run_file_based_workflow_to_lister(
        paper_pdf_path=paper_pdf_path,
        solution_pdf_path=solution_pdf_path,
        exam_id=exam_id,
        output_dir=output_dir
    )


# Aliases for backward compatibility
process_exam_file_based = process_exam_to_lister
process_exam = process_exam_to_lister

