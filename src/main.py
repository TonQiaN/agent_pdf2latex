"""
Main Entry Point for Agent PDF2LaTeX
Provides command-line interface for file management
"""

import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# 确保可以导入 src 模块, 自动搜索项目下src的模块, 并添加到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from openai import AsyncOpenAI
from src.services import FileManager


async def main():
    """
    主程序调用pdf2latex.py文件,实现pdf2latex功能
    """
    # 加载环境变量
    load_dotenv()
    
    # 暂时使用固定的文件路径
    project_root = Path(__file__).parent.parent
    paper_pdf = project_root / ".example" / "paper.pdf"
    solution_pdf = project_root / ".example" / "solution.pdf"
    
    print("=" * 70)
    print("🚀 Agent PDF2LaTeX")
    print("=" * 70)
    
    # 初始化 OpenAI 客户端和文件管理器
    openai_client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    file_manager = FileManager(openai_client)
    
    print("*" * 30 + "Step 1: Upload PDF files to OpenAI" + "*" * 30)

    # 上传 PDF 文件
    print(f"\n⏫ 上传试卷 PDF: {paper_pdf}")
    paper_file_id = await file_manager.upload_if_needed(
        path=str(paper_pdf),
        cache_key="paper_example"
    )
    print(f"✅ Paper File ID: {paper_file_id}")
    
    print(f"\n⏫ 上传答案 PDF: {solution_pdf}")
    solution_file_id = await file_manager.upload_if_needed(
        path=str(solution_pdf),
        cache_key="solution_example"
    )
    print(f"✅ Solution File ID: {solution_file_id}")
    print()
    print("✅ 文件上传完成")
    print("=" * 70)


def cli():
    # 运行主程序
    try:
        asyncio.run(main())
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    cli()
