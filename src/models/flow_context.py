"""
PDFWorkflowContext - Agent State for PDF to LaTeX Workflow

设计理念：
- ShortMemory (AgentState): 仅管理 file_id（通过 checkpointer 自动持久化）
- PDFWorkflowContext: 所有其他状态通过 context 传入（包括 exam_type、step 等）
"""

from langchain.agents import AgentState
from typing import Optional, Literal, List, Dict, Any
from dataclasses import dataclass, field

@dataclass
class FileRef:
    file_id: str
    mime_type: str = "application/pdf"
    extras: Dict[str, Any] = field(default_factory=dict)

class ShortMemory(AgentState):
    """
    短期记忆 - 管理文件引用
    """
    # ========== 文件 ID（跨步骤保持） ==========
    paper: FileRef      # Paper PDF
    solution: FileRef   # Solution PDF


@dataclass
class PDFWorkflowContext:
    """
    工作流状态 - 通过 context 参数传入
    
    包含所有业务逻辑相关的状态（不持久化）
    """
    # ========== 步骤控制 ==========
    step: Literal["classify", "lister"]         # 当前步骤
    exam_id: str                                # 试卷唯一标识
    
    # ========== Classify 结果 ==========
    exam_type: Optional[Literal["type1", "type2"]] = None
    classify_reasoning: Optional[str] = None
    classify_confidence: Optional[float] = None
    
    # ========== Lister 结果 ==========
    total_questions: int = 0
    questions: List[Dict[str, Any]] = field(default_factory=list)
    # 每个 question 格式：
    # {
    #   "question_index": int,
    #   "question_label": str,
    # }

__all__ = [
    "ShortMemory",
    "PDFWorkflowContext",
    "FileRef",
]
