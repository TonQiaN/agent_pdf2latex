"""File uploader service for OpenAI (using Vector Stores like import_v3)"""

from pathlib import Path
from typing import Dict, Optional
from openai import AsyncOpenAI
from loguru import logger

from ..config.settings import settings


class FileUploadResult:
    """文件上传结果 (Vector Store 方式)"""
    def __init__(
        self,
        paper_vector_store_id: str,
        solution_vector_store_id: str,
        paper_vector_store,
        solution_vector_store
    ):
        self.paper_vector_store_id = paper_vector_store_id
        self.solution_vector_store_id = solution_vector_store_id
        self.paper_vector_store = paper_vector_store
        self.solution_vector_store = solution_vector_store
        
        # 向后兼容的别名
        self.paper_file_id = paper_vector_store_id
        self.solution_file_id = solution_vector_store_id
    
    def to_dict(self) -> Dict[str, str]:
        return {
            "paper_vector_store_id": self.paper_vector_store_id,
            "solution_vector_store_id": self.solution_vector_store_id
        }


async def upload_pdfs_get_file_ids(
    paper_pdf_path: str,
    solution_pdf_path: str,
    client: Optional[AsyncOpenAI] = None
) -> FileUploadResult:
    """
    上传PDF到OpenAI Vector Stores（与 import_v3 相同的方式）
    
    Args:
        paper_pdf_path: Paper PDF路径
        solution_pdf_path: Solution PDF路径
        client: 可选的OpenAI客户端（用于复用连接）
    
    Returns:
        FileUploadResult: 包含 vector_store_id 的结果对象
    
    Raises:
        FileNotFoundError: PDF文件不存在
        Exception: 上传失败
    """
    # 验证文件存在
    paper_path = Path(paper_pdf_path)
    solution_path = Path(solution_pdf_path)
    
    if not paper_path.exists():
        raise FileNotFoundError(f"Paper PDF not found: {paper_pdf_path}")
    if not solution_path.exists():
        raise FileNotFoundError(f"Solution PDF not found: {solution_pdf_path}")
    
    # 创建客户端
    if client is None:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    logger.info("📤 Creating vector stores and uploading PDFs...")
    
    # Create vector store for paper PDF
    logger.info(f"  Creating vector store for paper PDF...")
    paper_vector_store = await client.vector_stores.create(name="ExamPaper")
    logger.info(f"  ✓ Paper vector store created: {paper_vector_store.id}")
    
    try:
        logger.info(f"  Uploading paper PDF: {paper_path.name} ({paper_path.stat().st_size / 1024:.1f} KB)")
        with open(paper_pdf_path, 'rb') as f:
            await client.vector_stores.file_batches.upload_and_poll(
                vector_store_id=paper_vector_store.id,
                files=[f]
            )
        logger.info(f"  ✓ Paper PDF uploaded to vector store")
    except Exception as e:
        logger.error(f"Failed to upload paper PDF: {e}")
        # 清理 vector store
        try:
            await client.vector_stores.delete(paper_vector_store.id)
        except:
            pass
        raise
    
    # Create vector store for solution PDF
    logger.info(f"  Creating vector store for solution PDF...")
    solution_vector_store = await client.vector_stores.create(name="ExamSolution")
    logger.info(f"  ✓ Solution vector store created: {solution_vector_store.id}")
    
    try:
        logger.info(f"  Uploading solution PDF: {solution_path.name} ({solution_path.stat().st_size / 1024:.1f} KB)")
        with open(solution_pdf_path, 'rb') as f:
            await client.vector_stores.file_batches.upload_and_poll(
                vector_store_id=solution_vector_store.id,
                files=[f]
            )
        logger.info(f"  ✓ Solution PDF uploaded to vector store")
    except Exception as e:
        logger.error(f"Failed to upload solution PDF: {e}")
        # 清理已创建的 vector stores
        try:
            await client.vector_stores.delete(paper_vector_store.id)
            logger.info(f"  ✓ Cleaned up paper vector store")
        except:
            pass
        try:
            await client.vector_stores.delete(solution_vector_store.id)
        except:
            pass
        raise
    
    return FileUploadResult(
        paper_vector_store_id=paper_vector_store.id,
        solution_vector_store_id=solution_vector_store.id,
        paper_vector_store=paper_vector_store,
        solution_vector_store=solution_vector_store
    )


async def cleanup_files(
    vector_store_ids: list[str],
    client: Optional[AsyncOpenAI] = None
):
    """
    清理上传的 Vector Stores
    
    Args:
        vector_store_ids: Vector Store ID 列表
        client: 可选的OpenAI客户端
    """
    if client is None:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    logger.info(f"🧹 Cleaning up {len(vector_store_ids)} vector stores...")
    
    for vs_id in vector_store_ids:
        try:
            await client.vector_stores.delete(vs_id)
            logger.info(f"✓ Vector store deleted: {vs_id}")
        except Exception as e:
            logger.warning(f"Failed to delete vector store {vs_id}: {e}")


async def verify_file_exists(
    vector_store_id: str,
    client: Optional[AsyncOpenAI] = None
) -> bool:
    """
    验证 Vector Store 是否存在于OpenAI
    
    Args:
        vector_store_id: Vector Store ID
        client: 可选的OpenAI客户端
    
    Returns:
        True if vector store exists, False otherwise
    """
    if client is None:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    try:
        vs_info = await client.vector_stores.retrieve(vector_store_id)
        logger.info(f"✓ Vector store exists: {vector_store_id} ({vs_info.name})")
        return True
    except Exception as e:
        logger.warning(f"Vector store not found: {vector_store_id} ({e})")
        return False

