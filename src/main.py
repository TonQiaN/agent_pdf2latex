"""
Main Entry Point for Agent PDF2LaTeX
Provides command-line interface for file management
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 确保可以导入 src 模块, 自动搜索项目下src的模块, 并添加到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from openai import OpenAI
from src.services import FileManager
from src.models.agent import create_pdf_agent, run_classify_step, run_lister_step


def main():
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
    openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    file_manager = FileManager(openai_client)
    
    print("*" * 30 + "Step 1: Upload PDF files to OpenAI" + "*" * 30)

    # 上传 PDF 文件
    print(f"\n⏫ 上传试卷 PDF: {paper_pdf}")
    paper_file_id = file_manager.upload_if_needed(
        path=str(paper_pdf),
        cache_key="paper_example"
    )
    print(f"✅ Paper File ID: {paper_file_id}")
    
    print(f"\n⏫ 上传答案 PDF: {solution_pdf}")
    solution_file_id = file_manager.upload_if_needed(
        path=str(solution_pdf),
        cache_key="solution_example"
    )
    print(f"✅ Solution File ID: {solution_file_id}")
    print()
    print("✅ 文件上传完成")
    print("=" * 70)

    agent = create_pdf_agent()
    
    # # Step 1: Classify
    # print("\n" + "=" * 70)
    # print("📋 Step 1: Classify")
    # print("=" * 70)
    # result_1 = run_classify_step(
    #     agent=agent,
    #     paper_file_id=paper_file_id,
    #     solution_file_id=solution_file_id,
    #     exam_id="exam_001"
    # )
    
    # # 打印结果
    # classify_response = result_1["messages"][-1].content
    # print(f"\n✅ Classify 结果:")
    # print(f"   类型: {type(classify_response)}")
    # print(f"   内容: {classify_response}")
    
    # # 如果是字符串，尝试解析 JSON
    # if isinstance(classify_response, str):
    #     import json
    #     try:
    #         # 尝试提取 JSON（可能包含 markdown 代码块）
    #         if "```json" in classify_response:
    #             json_str = classify_response.split("```json")[1].split("```")[0].strip()
    #         elif "```" in classify_response:
    #             json_str = classify_response.split("```")[1].split("```")[0].strip()
    #         else:
    #             json_str = classify_response.strip()
            
    #         classify_data = json.loads(json_str)
    #         print(f"\n   Exam Type: {classify_data.get('exam_type')}")
    #         print(f"   Reasoning: {classify_data.get('reasoning')}")
    #         if classify_data.get('confidence'):
    #             print(f"   Confidence: {classify_data.get('confidence')}")
    #         exam_type = classify_data.get('exam_type')
    #     except Exception as e:
    #         print(f"   ❌ JSON 解析失败: {e}")
    #         exam_type = None
    # else:
    #     # 如果是 Pydantic 对象
    #     print(f"   Exam Type: {classify_response.exam_type}")
    #     print(f"   Reasoning: {classify_response.reasoning}")
    #     if classify_response.confidence:
    #         print(f"   Confidence: {classify_response.confidence}")
    #     exam_type = classify_response.exam_type
    
    exam_type = "type1"
    # Step 2: Lister
    if exam_type:
        print("\n" + "=" * 70)
        print("📋 Step 2: Lister")
        print("=" * 70)
        result_2 = run_lister_step(
            agent=agent,
            paper_file_id=paper_file_id,
            # solution_file_id=solution_file_id,
            exam_id="exam_001",
            exam_type=exam_type
        )
        
        # 打印结果
        lister_response = result_2["messages"][-1].content
        print(f"\n✅ Lister 结果:")
        print(f"   类型: {type(lister_response)}")
        print(f"   内容: {lister_response}")
        
        # 如果是字符串，尝试解析 JSON
        if isinstance(lister_response, str):
            import json
            try:
                # 尝试提取 JSON（可能包含 markdown 代码块）
                if "```json" in lister_response:
                    json_str = lister_response.split("```json")[1].split("```")[0].strip()
                elif "```" in lister_response:
                    json_str = lister_response.split("```")[1].split("```")[0].strip()
                else:
                    json_str = lister_response.strip()
                
                lister_data = json.loads(json_str)
                print(f"\n   Total Questions: {lister_data.get('total_questions')}")
                print(f"   Questions:")
                for q in lister_data.get('questions', []):
                    print(f"      - Q{q.get('question_index')}: {q.get('question_label')}")
            except Exception as e:
                print(f"   ❌ JSON 解析失败: {e}")
        else:
            # 如果是 Pydantic 对象
            print(f"\n   Total Questions: {lister_response.total_questions}")
            print(f"   Questions:")
            for q in lister_response.questions:
                print(f"      - Q{q.question_index}: {q.question_label}")
    else:
        print("\n❌ 无法获取 exam_type，跳过 Lister 步骤")
    
    print("=" * 70)
    print("🏁 所有步骤完成")
    print("=" * 70)

def cli():
    # 运行主程序
    try:
        main()
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
