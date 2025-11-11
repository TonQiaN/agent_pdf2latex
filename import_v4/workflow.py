"""Complete workflow logic for V4 File-Based processing"""

import asyncio
import time
import base64
import json
from pathlib import Path
from typing import Optional
from datetime import datetime
from loguru import logger

from .config.settings import settings
from .models.schemas import QuestionList, QuestionListWithPages
from .preprocessing.pdf_renderer import preprocess_for_classification, add_page_markers_to_pdf
from .services.file_uploader import (
    upload_pdfs_get_file_ids,
    cleanup_files,
    FileUploadResult
)
from .agents._0_classifier_agent import classify_exam_type_direct
from .agents._1_question_lister_agent import list_all_questions_direct, list_all_questions_with_pages_direct, calculate_cost
from .agents import (
    generate_question_and_answer_latex_concurrent,
    label_question_direct,
)
from .utils.usage_tracker import UsageTracker
from .utils.image_extractor import extract_images_from_pdf
from .utils.latex_export import LatexExportUtility
from openai import AsyncOpenAI


async def run_file_based_workflow_to_lister(
    paper_pdf_path: str,
    solution_pdf_path: str,
    exam_id: Optional[str] = None,
    output_dir: Optional[str] = None
) -> dict:
    """
    执行V4 File-Based Workflow（仅到 Lister 阶段）
    
    这是一个简化版本，用于测试前几个步骤：
    1. 轻量级预处理（倒数第2、4、6页用于分类）
    2. 分类器判断试卷类型
    3. 上传PDF获取file_id
    4. Question Lister列出所有题目
    
    Args:
        paper_pdf_path: Paper PDF路径
        solution_pdf_path: Solution PDF路径
        exam_id: 试卷ID（可选，默认使用时间戳）
        output_dir: 输出目录（可选）
    
    Returns:
        包含处理结果的字典：
        {
            "exam_id": str,
            "exam_type": str,
            "question_list": QuestionList,
            "paper_file_id": str,
            "solution_file_id": str,
            "processing_time_seconds": float
        }
    """
    start_time = time.time()
    
    # === Setup ===
    if exam_id is None:
        exam_id = f"exam_{int(time.time())}"
    
    if output_dir is None:
        output_dir = Path(settings.output_dir) / exam_id
    else:
        output_dir = Path(output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info("="*80)
    logger.info(f"🚀 V4 File-Based Workflow (To Lister) - Starting")
    logger.info("="*80)
    logger.info(f"Exam ID: {exam_id}")
    logger.info(f"Paper: {paper_pdf_path}")
    logger.info(f"Solution: {solution_pdf_path}")
    logger.info(f"Output: {output_dir}")
    logger.info(f"Model: {settings.openai_model}")
    logger.info("="*80)
    
    # 初始化变量
    paper_file_id = None
    solution_file_id = None
    
    # 创建 Usage Tracker
    usage_tracker = UsageTracker(model=settings.openai_model)
    
    try:
        # === Step 1: 轻量级预处理 ===
        logger.info("\n" + "="*80)
        logger.info("Step 1: Lightweight Preprocessing (Classification Only)")
        logger.info("="*80)
        
        classification_data = await preprocess_for_classification(paper_pdf_path)
        logger.info(f"✓ Step 1 complete - Rendered {len(classification_data['selected_pages'])} pages")
        
        # 保存用于分类的图片到output目录
        classification_images_dir = output_dir / "classification_images"
        classification_images_dir.mkdir(parents=True, exist_ok=True)
        
        for idx, page_data in enumerate(classification_data['selected_pages'], start=1):
            image_filename = f"classification_page_{page_data['page_number']}.png"
            image_path = classification_images_dir / image_filename
            
            # 解码base64并保存
            image_bytes = base64.b64decode(page_data['image_base64'])
            image_path.write_bytes(image_bytes)
            
            logger.info(f"   Saved classification image: {image_filename}")
        
        logger.info(f"✓ Saved {len(classification_data['selected_pages'])} classification images to: {classification_images_dir}")
        
        # === Step 2: 分类器 ===
        logger.info("\n" + "="*80)
        logger.info("Step 2: Exam Type Classification")
        logger.info("="*80)
        
        exam_type, classifier_usage = await classify_exam_type_direct(classification_data)
        
        usage_tracker.add_step_usage(
            "classify_exam_type",
            classifier_usage.usage,
            {"exam_type": exam_type},
            duration_seconds=classifier_usage.duration_seconds
        )
        logger.info(f"✓ Step 2 complete - Exam type: {exam_type}")
        
        # === Step 3: 上传 PDF 文件获取 file_id（直接API方式）===
        logger.info("\n" + "="*80)
        logger.info("Step 3: Uploading PDFs to get file IDs (Direct API)")
        logger.info("="*80)
        
        # 创建 OpenAI 客户端
        openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
        
        # 上传 paper PDF
        logger.info(f"  Uploading paper PDF: {Path(paper_pdf_path).name}")
        with open(paper_pdf_path, 'rb') as f:
            paper_file = await openai_client.files.create(
                file=f,
                purpose="assistants"
            )
        logger.info(f"  ✓ Paper file uploaded: {paper_file.id}")
        
        # 上传 solution PDF
        logger.info(f"  Uploading solution PDF: {Path(solution_pdf_path).name}")
        with open(solution_pdf_path, 'rb') as f:
            solution_file = await openai_client.files.create(
                file=f,
                purpose="assistants"
            )
        logger.info(f"  ✓ Solution file uploaded: {solution_file.id}")
        
        paper_file_id = paper_file.id
        solution_file_id = solution_file.id
        
        logger.info(f"✓ Step 3 complete")
        
        # === Step 4: Question Lister（使用直接API方式）===
        logger.info("\n" + "="*80)
        logger.info("Step 4: Listing All Questions (Direct API)")
        logger.info("="*80)
        
        question_list, lister_usage = await list_all_questions_direct(
            exam_type=exam_type,
            paper_file_id=paper_file_id
        )
        
        usage_tracker.add_step_usage(
            "list_all_questions",
            lister_usage.usage,
            {"total_questions": question_list.total_questions},
            duration_seconds=lister_usage.duration_seconds
        )
        logger.info(f"✓ Step 4 complete - Found {question_list.total_questions} questions")
        
        # 保存题目清单
        if settings.save_question_list:
            question_list_file = output_dir / "question_list.json"
            question_list_file.write_text(
                question_list.model_dump_json(indent=2),
                encoding='utf-8'
            )
            logger.info(f"   Saved question list to: {question_list_file}")
        
        # === 最终总结 ===
        processing_time = time.time() - start_time
        
        # 获取 usage 汇总
        usage_summary = usage_tracker.get_summary()
        
        logger.info("\n" + "="*80)
        logger.info("✅ Processing Complete (To Lister Stage)!")
        logger.info("="*80)
        logger.info(f"Exam ID: {exam_id}")
        logger.info(f"Exam Type: {exam_type}")
        logger.info(f"Total Questions Found: {question_list.total_questions}")
        logger.info(f"Processing Time: {processing_time:.1f}s")
        logger.info(f"Output Directory: {output_dir}")
        logger.info("")
        logger.info("📊 API Usage Summary:")
        logger.info(f"   Model: {usage_summary['model']}")
        logger.info(f"   Total Requests: {usage_summary['total']['requests']}")
        logger.info(f"   Total Tokens: {usage_summary['total']['total_tokens']:,} (input: {usage_summary['total']['input_tokens']:,}, output: {usage_summary['total']['output_tokens']:,})")
        logger.info(f"   Total Duration: {usage_summary['total']['total_duration_seconds']:.2f}s")
        logger.info(f"   Estimated Cost: ${usage_summary['total']['estimated_cost_usd']:.4f}")
        logger.info("")
        logger.info("   By Step:")
        for step_name, step_data in usage_summary['steps'].items():
            logger.info(f"     {step_name}:")
            logger.info(f"       Duration: {step_data['duration_seconds']:.2f}s")
            logger.info(f"       Tokens: {step_data['total_tokens']:,} (input: {step_data['input_tokens']:,}, output: {step_data['output_tokens']:,})")
            logger.info(f"       Cost: ${step_data['estimated_cost_usd']:.4f}")
        logger.info("="*80)
        
        # 返回结果
        result = {
            "exam_id": exam_id,
            "exam_type": exam_type,
            "question_list": question_list,
            "paper_file_id": paper_file_id,  # 使用 file_id 而不是 vector_store_id
            "solution_file_id": solution_file_id,
            "processing_time_seconds": processing_time,
            "output_dir": str(output_dir),
            "api_usage": usage_summary
        }
        
        # 保存结果摘要
        result_file = output_dir / f"{exam_id}_lister_result.json"
        import json
        result_file.write_text(
            json.dumps({
                "exam_id": result["exam_id"],
                "exam_type": result["exam_type"],
                "total_questions": question_list.total_questions,
                "questions": [
                    {"index": q.question_index, "label": q.question_label}
                    for q in question_list.questions
                ],
                "paper_file_id": result["paper_file_id"],
                "solution_file_id": result["solution_file_id"],
                "processing_time_seconds": result["processing_time_seconds"],
                "api_usage": usage_summary
            }, indent=2),
            encoding='utf-8'
        )
        logger.info(f"✓ Result saved to: {result_file}")
        
        return result
        
    finally:
        # === 清理上传的文件（可选） ===
        if settings.auto_cleanup_files and 'paper_file_id' in locals():
            logger.info("\n" + "="*80)
            logger.info("Cleaning Up Uploaded Files")
            logger.info("="*80)
            
            try:
                openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
                await openai_client.files.delete(paper_file_id)
                logger.info(f"✓ Deleted paper file: {paper_file_id}")
                await openai_client.files.delete(solution_file_id)
                logger.info(f"✓ Deleted solution file: {solution_file_id}")
            except Exception as e:
                logger.warning(f"Failed to cleanup files: {e}")


async def run_complete_workflow(
    paper_pdf_path: str,
    solution_pdf_path: str,
    subject_id: int,
    grade_id: int,
    exam_id: Optional[str] = None,
    output_dir: Optional[str] = None
) -> dict:
    """
    执行完整的 V4 File-Based Workflow
    
    完整流程包括：
    1. 轻量级预处理（倒数第2、4、6页用于分类）
    2. 分类器判断试卷类型
    3. 上传PDF获取file_id
    4. Question Lister列出所有题目
    5. 对每个题目：
       - 生成 Question LaTeX
       - 生成 Answer LaTeX
       - 标注题目（topic, subtopic, type, difficulty, mark）
    
    Args:
        paper_pdf_path: Paper PDF路径
        solution_pdf_path: Solution PDF路径
        subject_id: Subject ID（用于标注）
        grade_id: Grade ID（用于标注）
        exam_id: 试卷ID（可选，默认使用时间戳）
        output_dir: 输出目录（可选）
    
    Returns:
        包含处理结果的字典：
        {
            "exam_id": str,
            "exam_type": str,
            "question_list": QuestionList,
            "paper_file_id": str,
            "solution_file_id": str,
            "questions_results": List[dict],
            "processing_time_seconds": float,
            "api_usage": dict
        }
    """
    start_time = time.time()
    
    # === Setup ===
    if exam_id is None:
        exam_id = f"exam_{int(time.time())}"
    
    if output_dir is None:
        output_dir = Path(settings.output_dir) / exam_id
    else:
        output_dir = Path(output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info("="*80)
    logger.info(f"🚀 V4 Complete File-Based Workflow - Starting")
    logger.info("="*80)
    logger.info(f"Exam ID: {exam_id}")
    logger.info(f"Paper: {paper_pdf_path}")
    logger.info(f"Solution: {solution_pdf_path}")
    logger.info(f"Subject ID: {subject_id}, Grade ID: {grade_id}")
    logger.info(f"Output: {output_dir}")
    logger.info(f"Model: {settings.openai_model}")
    logger.info("="*80)
    
    # 初始化变量
    paper_file_id = None
    solution_file_id = None
    paper_marked_file_id = None
    solution_marked_file_id = None
    paper_marked_path = None
    solution_marked_path = None
    openai_client = None
    
    # 创建 Usage Tracker
    usage_tracker = UsageTracker(model=settings.openai_model)
    
    try:
        # === Step 1: 轻量级预处理 ===
        logger.info("\n" + "="*80)
        logger.info("Step 1: Lightweight Preprocessing (Classification Only)")
        logger.info("="*80)
        
        classification_data = await preprocess_for_classification(paper_pdf_path)
        logger.info(f"✓ Step 1 complete - Rendered {len(classification_data['selected_pages'])} pages")
        
        # 保存用于分类的图片到output目录
        classification_images_dir = output_dir / "classification_images"
        classification_images_dir.mkdir(parents=True, exist_ok=True)
        
        for idx, page_data in enumerate(classification_data['selected_pages'], start=1):
            image_filename = f"classification_page_{page_data['page_number']}.png"
            image_path = classification_images_dir / image_filename
            
            # 解码base64并保存
            image_bytes = base64.b64decode(page_data['image_base64'])
            image_path.write_bytes(image_bytes)
            
            logger.info(f"   Saved classification image: {image_filename}")
        
        logger.info(f"✓ Saved {len(classification_data['selected_pages'])} classification images to: {classification_images_dir}")
        
        # === Step 2: 分类器 ===
        logger.info("\n" + "="*80)
        logger.info("Step 2: Exam Type Classification")
        logger.info("="*80)
        
        exam_type, classifier_usage = await classify_exam_type_direct(classification_data)
        
        usage_tracker.add_step_usage(
            "classify_exam_type",
            classifier_usage.usage,
            {"exam_type": exam_type},
            duration_seconds=classifier_usage.duration_seconds
        )
        logger.info(f"✓ Step 2 complete - Exam type: {exam_type}")
        
        # === Step 3: 上传 PDF 文件获取 file_id（直接API方式）===
        logger.info("\n" + "="*80)
        logger.info("Step 3: Uploading PDFs to get file IDs (Direct API)")
        logger.info("="*80)
        
        # 创建 OpenAI 客户端
        openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
        
        # 上传 paper PDF
        logger.info(f"  Uploading paper PDF: {Path(paper_pdf_path).name}")
        with open(paper_pdf_path, 'rb') as f:
            paper_file = await openai_client.files.create(
                file=f,
                purpose="assistants"
            )
        logger.info(f"  ✓ Paper file uploaded: {paper_file.id}")
        
        # 上传 solution PDF
        logger.info(f"  Uploading solution PDF: {Path(solution_pdf_path).name}")
        with open(solution_pdf_path, 'rb') as f:
            solution_file = await openai_client.files.create(
                file=f,
                purpose="assistants"
            )
        logger.info(f"  ✓ Solution file uploaded: {solution_file.id}")
        
        paper_file_id = paper_file.id
        solution_file_id = solution_file.id
        
        logger.info(f"✓ Step 3 complete")
        
        # === Step 4: Question Lister（使用带页码的版本）===
        logger.info("\n" + "="*80)
        logger.info("Step 4: Listing All Questions with Page Locations")
        logger.info("="*80)
        
        question_list_with_pages, lister_usage, lister_usage_breakdown = await list_all_questions_with_pages_direct(
            exam_type=exam_type,
            paper_pdf_path=paper_pdf_path,
            solution_pdf_path=solution_pdf_path
        )
        
        # Add lister usage to tracker (use total usage, duration will be calculated from individual steps)
        usage_tracker.add_step_usage(
            "list_all_questions",
            lister_usage,
            {"total_questions": question_list_with_pages.total_questions},
            duration_seconds=0  # Duration is tracked in breakdown, but we use total usage here
        )
        logger.info(f"✓ Step 4 complete - Found {question_list_with_pages.total_questions} questions with page locations")
        
        # 保存题目清单
        if settings.save_question_list:
            question_list_file = output_dir / "question_list.json"
            question_list_file.write_text(
                question_list_with_pages.model_dump_json(indent=2),
                encoding='utf-8'
            )
            logger.info(f"   Saved question list to: {question_list_file}")
        
        # 使用带页码的题目列表
        question_list = question_list_with_pages
        
        # === Step 5: Process each question ===
        logger.info("\n" + "="*80)
        logger.info(f"Step 5: Processing All Questions (LaTeX Generation + Labelling)")
        logger.info("="*80)
        
        # Note: openai_client already created in Step 3
        
        # Add page markers to PDFs for LaTeX generation
        temp_dir = output_dir / "temp_marked_pdfs"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        paper_marked_path = temp_dir / f"paper_marked_{timestamp}.pdf"
        solution_marked_path = temp_dir / f"solution_marked_{timestamp}.pdf"
        
        logger.info("Adding page markers to PDFs...")
        add_page_markers_to_pdf(paper_pdf_path, str(paper_marked_path), zero_based=True)
        add_page_markers_to_pdf(solution_pdf_path, str(solution_marked_path), zero_based=True)
        
        # Upload marked PDFs
        with open(paper_marked_path, 'rb') as f:
            paper_marked_file = await openai_client.files.create(file=f, purpose="assistants")
        with open(solution_marked_path, 'rb') as f:
            solution_marked_file = await openai_client.files.create(file=f, purpose="assistants")
        
        paper_marked_file_id = paper_marked_file.id
        solution_marked_file_id = solution_marked_file.id
        
        logger.info(f"✓ Uploaded marked PDFs")
        logger.info(f"  Paper marked file ID: {paper_marked_file_id}")
        logger.info(f"  Solution marked file ID: {solution_marked_file_id}")
        
        # Process each question
        # Define async function to process a single question
        async def process_single_question(question_item, idx):
            """Process a single question: generate LaTeX, extract images, save JSON"""
            logger.info(f"\n{'='*80}")
            logger.info(f"[{idx}/{question_list.total_questions}] Processing: {question_item.question_label}")
            logger.info(f"{'='*80}")
            logger.info(f"  Question Index: {question_item.question_index}")
            logger.info(f"  Paper Pages: {question_item.paper_pages}")
            logger.info(f"  Solution Pages: {question_item.solution_pages}")
            
            try:
                # Generate LaTeX and Label (concurrent LaTeX + sequential labelling)
                q_latex, a_latex, label_output, q_usage, a_usage, label_usage = await generate_question_and_answer_latex_concurrent(
                    question_label=question_item.question_label,
                    paper_pages=question_item.paper_pages,
                    solution_pages=question_item.solution_pages,
                    paper_file_id=paper_marked_file_id,
                    solution_file_id=solution_marked_file_id,
                    question_index=question_item.question_index,
                    subject_id=subject_id,
                    grade_id=grade_id,
                    enable_labelling=True
                )
                
                q_cost = calculate_cost(q_usage.usage)
                a_cost = calculate_cost(a_usage.usage)
                label_cost = calculate_cost(label_usage.usage) if label_usage else 0.0
                
                logger.info(f"  ✓ [{idx}/{question_list.total_questions}] Complete processing finished")
                logger.info(f"    Question: {len(q_latex.question_latex)} chars, {len(q_latex.question_images)} images")
                logger.info(f"    Answer: {len(a_latex.answer_latex)} chars, {len(a_latex.answer_images)} images, marks: {a_latex.marks}")
                if label_output:
                    logger.info(f"    Label: Topic {label_output.topic_id}, Subtopic {label_output.subtopic_id}, Type: {label_output.question_type}, Difficulty: {label_output.difficulty}")
                
                # Extract images from PDF (for LaTeX export)
                images_dir = output_dir / "extracted_images" / f"question_{question_item.question_index}"
                images_dir.mkdir(parents=True, exist_ok=True)
                
                # Extract question images
                if q_latex.question_images:
                    logger.info(f"  Extracting {len(q_latex.question_images)} question images...")
                    updated_q_images = extract_images_from_pdf(
                        pdf_path=paper_pdf_path,
                        images_info=q_latex.question_images,
                        output_dir=images_dir,
                        prefix=f"q{question_item.question_index}_image"
                    )
                    # Update image paths to absolute paths
                    for img in updated_q_images:
                        if img.image_path:
                            img.image_path = str(images_dir / img.image_path)
                    q_latex.question_images = updated_q_images
                    logger.info(f"  ✓ Extracted {len(updated_q_images)} question images")
                
                # Extract answer images
                if a_latex.answer_images:
                    logger.info(f"  Extracting {len(a_latex.answer_images)} answer images...")
                    updated_a_images = extract_images_from_pdf(
                        pdf_path=solution_pdf_path,
                        images_info=a_latex.answer_images,
                        output_dir=images_dir,
                        prefix=f"s{question_item.question_index}_image"
                    )
                    # Update image paths to absolute paths
                    for img in updated_a_images:
                        if img.image_path:
                            img.image_path = str(images_dir / img.image_path)
                    a_latex.answer_images = updated_a_images
                    logger.info(f"  ✓ Extracted {len(updated_a_images)} answer images")
                
                # Note: LaTeX outputs will be collected after all questions are processed
                
                # Save individual question JSON
                safe_label = question_item.question_label.replace('(', '').replace(')', '').replace(' ', '_')
                question_json_file = output_dir / f"question_{safe_label}.json"
                
                question_data = {
                    "metadata": {
                        "timestamp": datetime.now().isoformat(),
                        "model": settings.openai_model,
                        "question_index": label_output.question_index if label_output else question_item.question_index,
                        "question_label": label_output.question_label if label_output else question_item.question_label,
                    },
                    "question_latex": {
                        "question_label": q_latex.question_label,
                        "question_latex": q_latex.question_latex,
                        "question_images": [img.model_dump() for img in q_latex.question_images],
                        "compilation_success": q_latex.compilation_success,
                        "error_message": q_latex.error_message,
                    },
                    "answer_latex": {
                        "question_label": a_latex.question_label,
                        "answer_latex": a_latex.answer_latex,
                        "answer_images": [img.model_dump() for img in a_latex.answer_images],
                        "marks": a_latex.marks,
                        "compilation_success": a_latex.compilation_success,
                        "error_message": a_latex.error_message,
                    },
                    "label": {
                        "question_index": label_output.question_index if label_output else question_item.question_index,
                        "question_label": label_output.question_label if label_output else question_item.question_label,
                        "topic_id": label_output.topic_id if label_output else None,
                        "subtopic_id": label_output.subtopic_id if label_output else None,
                        "question_type": label_output.question_type if label_output else None,
                        "difficulty": label_output.difficulty if label_output else None,
                        "mark": label_output.mark if label_output else a_latex.marks,
                        "confidence": label_output.confidence if label_output else None,
                        "reasoning": label_output.reasoning if label_output else "",
                    },
                    "page_info": {
                        "paper_pages": question_item.paper_pages,
                        "solution_pages": question_item.solution_pages,
                    },
                    "usage": {
                        "question_latex": {
                            "duration_seconds": round(q_usage.duration_seconds, 2),
                            "input_tokens": q_usage.input_tokens,
                            "output_tokens": q_usage.output_tokens,
                            "total_tokens": q_usage.total_tokens,
                            "estimated_cost_usd": round(q_cost, 4)
                        },
                        "answer_latex": {
                            "duration_seconds": round(a_usage.duration_seconds, 2),
                            "input_tokens": a_usage.input_tokens,
                            "output_tokens": a_usage.output_tokens,
                            "total_tokens": a_usage.total_tokens,
                            "estimated_cost_usd": round(a_cost, 4)
                        },
                        "labelling": {
                            "duration_seconds": round(label_usage.duration_seconds, 2) if label_usage else 0,
                            "input_tokens": label_usage.input_tokens if label_usage else 0,
                            "output_tokens": label_usage.output_tokens if label_usage else 0,
                            "total_tokens": label_usage.total_tokens if label_usage else 0,
                            "estimated_cost_usd": round(label_cost, 4)
                        },
                        "total": {
                            "duration_seconds": round(
                                q_usage.duration_seconds + 
                                a_usage.duration_seconds + 
                                (label_usage.duration_seconds if label_usage else 0), 
                                2
                            ),
                            "total_tokens": (
                                q_usage.total_tokens + 
                                a_usage.total_tokens + 
                                (label_usage.total_tokens if label_usage else 0)
                            ),
                            "estimated_cost_usd": round(q_cost + a_cost + label_cost, 4)
                        }
                    }
                }
                
                with open(question_json_file, 'w', encoding='utf-8') as f:
                    json.dump(question_data, f, indent=2, ensure_ascii=False)
                
                logger.info(f"  ✓ Saved to: {question_json_file}")
                
                # Return results
                return {
                    "success": True,
                    "question_index": question_item.question_index,
                    "question_label": question_item.question_label,
                    "paper_pages": question_item.paper_pages,
                    "solution_pages": question_item.solution_pages,
                    "q_latex": q_latex,
                    "a_latex": a_latex,
                    "label": label_output.model_dump() if label_output else None,
                    "usage": question_data["usage"],
                    "costs": {
                        "q_cost": q_cost,
                        "a_cost": a_cost,
                        "label_cost": label_cost
                    }
                }
                
            except Exception as e:
                logger.error(f"  ✗ [{idx}/{question_list.total_questions}] Failed to process {question_item.question_label}: {e}")
                import traceback
                logger.error(f"  Traceback: {traceback.format_exc()}")
                return {
                    "success": False,
                    "question_index": question_item.question_index,
                    "question_label": question_item.question_label,
                    "paper_pages": question_item.paper_pages,
                    "solution_pages": question_item.solution_pages,
                    "error": str(e)
                }
        
        # === Concurrent Processing of All Questions ===
        logger.info(f"\n{'='*80}")
        logger.info(f"🚀 Starting CONCURRENT processing of {question_list.total_questions} questions")
        logger.info(f"{'='*80}")
        
        # Create tasks for all questions
        tasks = [
            process_single_question(question_item, idx)
            for idx, question_item in enumerate(question_list.questions, start=1)
        ]
        
        # Execute all tasks concurrently
        concurrent_start = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        concurrent_duration = time.time() - concurrent_start
        
        # Process results
        all_questions_results = []
        all_question_latex = []
        all_answer_latex = []
        total_q_cost = 0.0
        total_a_cost = 0.0
        total_label_cost = 0.0
        successful_count = 0
        failed_count = 0
        
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Unexpected exception in concurrent processing: {result}")
                failed_count += 1
                all_questions_results.append({
                    "error": str(result)
                })
            elif result.get("success"):
                successful_count += 1
                # Collect LaTeX outputs
                all_question_latex.append(result["q_latex"])
                all_answer_latex.append(result["a_latex"])
                # Accumulate costs
                total_q_cost += result["costs"]["q_cost"]
                total_a_cost += result["costs"]["a_cost"]
                total_label_cost += result["costs"]["label_cost"]
                # Add to results (remove internal data)
                result_copy = result.copy()
                result_copy.pop("q_latex", None)
                result_copy.pop("a_latex", None)
                result_copy.pop("costs", None)
                result_copy.pop("success", None)
                all_questions_results.append(result_copy)
            else:
                failed_count += 1
                all_questions_results.append({
                    "question_index": result.get("question_index"),
                    "question_label": result.get("question_label"),
                    "error": result.get("error")
                })
        
        logger.info(f"\n{'='*80}")
        logger.info(f"✅ CONCURRENT processing completed!")
        logger.info(f"{'='*80}")
        logger.info(f"  Total duration: {concurrent_duration:.2f}s")
        logger.info(f"  Successful: {successful_count}/{question_list.total_questions}")
        logger.info(f"  Failed: {failed_count}/{question_list.total_questions}")
        logger.info(f"  Average time per question: {concurrent_duration/question_list.total_questions:.2f}s")
        logger.info(f"{'='*80}")
        
        # === Final Summary ===
        processing_time = time.time() - start_time
        
        # Get workflow usage summary
        workflow_usage_summary = usage_tracker.get_summary()
        workflow_cost = workflow_usage_summary["total"]["estimated_cost_usd"]
        total_cost = workflow_cost + total_q_cost + total_a_cost + total_label_cost
        
        # Save complete results
        complete_result = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "model": settings.openai_model,
                "paper_pdf": paper_pdf_path,
                "solution_pdf": solution_pdf_path,
                "subject_id": subject_id,
                "grade_id": grade_id,
            },
            "workflow": {
                "exam_id": exam_id,
                "exam_type": exam_type,
                "total_questions": question_list.total_questions,
                "paper_file_id": paper_file_id,
                "solution_file_id": solution_file_id,
                "api_usage": workflow_usage_summary
            },
            "questions": all_questions_results,
            "summary": {
                "total_questions": question_list.total_questions,
                "processed_questions": len([q for q in all_questions_results if "error" not in q]),
                "failed_questions": len([q for q in all_questions_results if "error" in q]),
                "total_processing_time_seconds": round(processing_time, 2),
                "total_costs": {
                    "workflow": round(workflow_cost, 4),
                    "question_latex": round(total_q_cost, 4),
                    "answer_latex": round(total_a_cost, 4),
                    "labelling": round(total_label_cost, 4),
                    "total": round(total_cost, 4)
                }
            }
        }
        
        result_file = output_dir / "complete_result.json"
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(complete_result, f, indent=2, ensure_ascii=False)
        
        # === Export LaTeX Folder Structure ===
        latex_folder = None
        if all_question_latex and all_answer_latex:
            logger.info(f"\n{'='*80}")
            logger.info(f"Step 6: Exporting LaTeX Folder Structure")
            logger.info(f"{'='*80}")
            
            try:
                exporter = LatexExportUtility()
                
                # Construct exam_info from available data
                exam_info = {
                    'year': datetime.now().strftime('%Y'),
                    'school': 'Unknown',
                    'grade': str(grade_id),
                    'subject': f'Subject_{subject_id}',
                    'task': f'{exam_id}'
                }
                
                latex_folder = exporter.export_latex_to_folder(
                    question_latex_outputs=all_question_latex,
                    answer_latex_outputs=all_answer_latex,
                    output_dir=output_dir,
                    exam_info=exam_info
                )
                
                logger.info(f"✓ LaTeX folder exported to: {latex_folder}")
                logger.info(f"  You can now compile paper.tex and solutions.tex")
                
                # Update complete_result with latex_folder path
                complete_result["latex_folder"] = str(latex_folder)
                with open(result_file, 'w', encoding='utf-8') as f:
                    json.dump(complete_result, f, indent=2, ensure_ascii=False)
                    
            except Exception as e:
                logger.error(f"✗ Failed to export LaTeX folder: {e}")
                logger.exception(e)
                # Continue without failing the entire workflow
        
        logger.info(f"\n{'='*80}")
        logger.info(f"✅ Complete Workflow Finished!")
        logger.info(f"{'='*80}")
        logger.info(f"Exam ID: {exam_id}")
        logger.info(f"Exam Type: {exam_type}")
        logger.info(f"Total Questions: {question_list.total_questions}")
        logger.info(f"Processed: {len([q for q in all_questions_results if 'error' not in q])}")
        logger.info(f"Failed: {len([q for q in all_questions_results if 'error' in q])}")
        logger.info(f"Total Processing Time: {processing_time:.1f}s")
        logger.info(f"")
        logger.info(f"📊 Cost Summary:")
        logger.info(f"  Workflow: ${workflow_cost:.4f}")
        logger.info(f"  Question LaTeX: ${total_q_cost:.4f}")
        logger.info(f"  Answer LaTeX: ${total_a_cost:.4f}")
        logger.info(f"  Labelling: ${total_label_cost:.4f}")
        logger.info(f"  Total: ${total_cost:.4f}")
        logger.info(f"")
        logger.info(f"✓ Complete results saved to: {result_file}")
        logger.info(f"✓ Individual question files saved to: {output_dir}")
        if latex_folder:
            logger.info(f"✓ LaTeX folder exported to: {latex_folder}")
        logger.info(f"{'='*80}")
        
        # Return result
        result = {
            "exam_id": exam_id,
            "exam_type": exam_type,
            "question_list": question_list,
            "paper_file_id": paper_file_id,
            "solution_file_id": solution_file_id,
            "questions_results": all_questions_results,
            "processing_time_seconds": processing_time,
            "output_dir": str(output_dir),
            "latex_folder": str(latex_folder) if latex_folder else None,
            "api_usage": {
                "workflow": workflow_usage_summary,
                "question_latex_total_cost": total_q_cost,
                "answer_latex_total_cost": total_a_cost,
                "labelling_total_cost": total_label_cost,
                "total_cost": total_cost
            }
        }
        
        return result
        
    finally:
        # Clean up uploaded marked PDFs
        if paper_marked_file_id and openai_client:
            try:
                await openai_client.files.delete(paper_marked_file_id)
                await openai_client.files.delete(solution_marked_file_id)
                logger.info("\n✓ Cleaned up uploaded marked PDFs from OpenAI")
            except Exception as e:
                logger.warning(f"Failed to cleanup marked PDFs: {e}")
        
        # Clean up temporary marked PDFs
        if paper_marked_path and paper_marked_path.exists():
            paper_marked_path.unlink()
        if solution_marked_path and solution_marked_path.exists():
            solution_marked_path.unlink()
        if paper_marked_path or solution_marked_path:
            logger.info("✓ Cleaned up temporary marked PDFs")
        
        # Clean up original uploaded files (if auto_cleanup enabled)
        if settings.auto_cleanup_files and paper_file_id and openai_client:
            try:
                await openai_client.files.delete(paper_file_id)
                await openai_client.files.delete(solution_file_id)
                logger.info("✓ Cleaned up original uploaded PDFs from OpenAI")
            except Exception as e:
                logger.warning(f"Failed to cleanup original files: {e}")

