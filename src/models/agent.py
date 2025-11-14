"""
Agent Configuration for PDF to LaTeX Workflow
"""

from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver
from langchain.messages import HumanMessage
from typing import Optional, Dict, Any

from src.models.flow_context import ShortMemory, PDFWorkflowContext, FileRef
from src.prompts.dynamic_prompts import build_dynamic_system_prompt
from src.models.schemas import context_based_output

def create_pdf_agent(
    model_type: str = "openai",
    model: str = "gpt-4o",
    temperature: float = 0.0,
):
    """
    创建 PDF to LaTeX Agent
    
    支持步骤：
    - Step 0: classify - 分类试卷类型
    - Step 1: lister - 列出所有题目
    
    Args:
        model: OpenAI 模型名称（默认 "gpt-4o")  
        temperature: 生成温度（默认 0.0)
    
    Returns:
        LangChain Agent 实例
    
    Note:
        需要在环境变量中设置 OPENAI_API_KEY
    """
    # 1. 创建 LLM（自动从环境变量读取 OPENAI_API_KEY）
    if model_type == "openai":
        llm = ChatOpenAI(
        model=model,
        temperature=temperature,
        max_retries=3,      # 自动重试 3 次
        timeout=120.0,      # 超时时间 120 秒（处理 PDF 可能需要更长时间）
        request_timeout=120.0,  # 请求超时
    )
    elif model_type == "google":
        llm = ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            max_retries=3,      # 自动重试 3 次
            timeout=120.0,      # 超时时间 120 秒（处理 PDF 可能需要更长时间）
            request_timeout=120.0,  # 请求超时
        )

    # 2. 创建 Agent
    agent = create_agent(
        model=llm,
        tools=[],
        middleware=[
            build_dynamic_system_prompt,  # 动态 prompt
            context_based_output,  # 根据上下文选择输出格式
        ],
        state_schema=ShortMemory,
        context_schema=PDFWorkflowContext,
        checkpointer=InMemorySaver(),
    )

    return agent

def run_classify_step(
    agent,
    paper_file_id: str,
    solution_file_id: str,
    exam_id: str = "exam_001"
) -> Dict[str, Any]:
    """
    运行 Step 0: Classify

    Args:
        agent: LangChain Agent 实例
        paper_file_id: Paper PDF 文件 ID
        solution_file_id: Solution PDF 文件 ID
        exam_id: 试卷 ID（默认 "exam_001"）
    
    Returns:
        Classify 结果字典
    
    Note:
        使用 OpenAI 的 file_id 格式在 message content 中传递文件
    """
    message = HumanMessage(content=[
        {"type": "text", "text": "Analyze the exam type from these pages."},
        {"type": "file", "file_id": paper_file_id, "mime_type": "application/pdf",
            "extras": {"filename": "paper.pdf", "description": "Original exam paper"}},
        # {"type": "file", "file_id": solution_file_id, "mime_type": "application/pdf",
            # "extras": {"filename": "solution.pdf", "description": "Official solutions"}}
    ])


    result = agent.invoke(
        {"messages": [message]},
        state=ShortMemory(
            paper=FileRef(
                file_id=paper_file_id,
                mime_type="application/pdf",
                extras={"filename": "paper.pdf", "description": "Original exam paper"},
            ),
            # solution=FileRef(
            #     file_id=solution_file_id,
            #     mime_type="application/pdf",
            #     extras={"filename": "solution.pdf", "description": "Official solutions"},
            # ),
        ),
        context=PDFWorkflowContext(
            step="classify",
            exam_id=exam_id,
        ),
        config={"configurable": {"thread_id": exam_id}},
    )
    return result


def run_lister_step(
    agent,
    paper_file_id: str,
    # solution_file_id: str,
    exam_id: str = "exam_001",
    exam_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    运行 Step 1: Lister
    
    Args:
        agent: LangChain Agent 实例
        paper_file_id: Paper PDF 文件 ID
        solution_file_id: Solution PDF 文件 ID
        exam_id: 试卷 ID（默认 "exam_001"）
        exam_type: 试卷类型（如果已知，可以传入；否则需要先运行 classify）
    
    Returns:
        Lister 结果字典
    
    Note:
        使用 OpenAI 的 file_id 格式在 message content 中传递文件
    """

    message = HumanMessage(content=[
        {"type": "text", "text": "List the questions and their index in the paper."},
        {"type": "file", "file_id": paper_file_id, "mime_type": "application/pdf",
            "extras": {"filename": "paper.pdf", "description": "Original exam paper"}},
        # {"type": "file", "file_id": solution_file_id, "mime_type": "application/pdf",
        #     "extras": {"filename": "solution.pdf", "description": "Official solutions"}}
    ])

    result = agent.invoke(
        {"messages": [message]},
        context=PDFWorkflowContext(
            step="lister",
            exam_id=exam_id,
            exam_type=exam_type,
        ),
        config={"configurable": {"thread_id": exam_id}},
    )
    return result


# ========== 导出 ==========
__all__ = [
    "create_pdf_agent",
    "run_classify_step",
    "run_lister_step",
]
