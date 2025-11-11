"""Test LaTeX Generation with Image Extraction for Questions 5 and 6"""

import asyncio
import json
from pathlib import Path
from datetime import datetime
from openai import AsyncOpenAI

from src.services.services_v2.import_paper.import_v4.agents import (
    generate_question_and_answer_latex_concurrent,
    correct_image_bbox,
)
from src.services.services_v2.import_paper.import_v4.agents._1_question_lister_agent import (
    calculate_cost
)
from src.services.services_v2.import_paper.import_v4.preprocessing.pdf_renderer import (
    add_page_markers_to_pdf
)
from src.services.services_v2.import_paper.import_v4.utils.image_extractor import (
    extract_images_from_pdf
)
from src.services.services_v2.import_paper.import_v4.utils.latex_export import (
    LatexExportUtility
)
from src.services.services_v2.import_paper.import_v4.config.settings import settings
from src.logger import logger


# Test cases for questions 5 and 6
TEST_CASES = [
    {
        "question_label": "Question 5",
        "question_index": 5,
        "paper_pages": [3],  # 0-based
        "solution_pages": [0, 34],  # 0-based
    },
    {
        "question_label": "Question 6",
        "question_index": 6,
        "paper_pages": [4],  # 0-based
        "solution_pages": [0, 35],  # 0-based
    },
]


async def main():
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python -m src.services.services_v2.import_paper.import_v4.test_latex_with_images <paper_pdf> <solution_pdf>")
        print("\nThis script tests LaTeX generation with image extraction for Questions 5 and 6:")
        print("  1. Generate Question LaTeX")
        print("  2. Generate Answer LaTeX")
        print("  3. Extract images from PDF using bounding boxes")
        print("  4. Export complete LaTeX folder structure")
        sys.exit(1)
    
    paper_pdf = sys.argv[1]
    solution_pdf = sys.argv[2]
    
    logger.info(f"="*80)
    logger.info(f"Test LaTeX Generation with Image Extraction")
    logger.info(f"="*80)
    logger.info(f"Paper PDF: {paper_pdf}")
    logger.info(f"Solution PDF: {solution_pdf}")
    logger.info(f"Test Questions: Question 5, Question 6")
    logger.info(f"="*80)
    
    # Create output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    test_output_dir = Path("src/output/latex_tests") / f"latex_with_images_{timestamp}"
    test_output_dir.mkdir(parents=True, exist_ok=True)
    
    # Step 1: Add page markers to PDFs
    logger.info("\n" + "="*80)
    logger.info("Step 1: Adding page markers to PDFs...")
    logger.info("="*80)
    
    temp_dir = Path("src/output/temp_latex_tests")
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    paper_marked_path = temp_dir / f"paper_marked_{timestamp}.pdf"
    solution_marked_path = temp_dir / f"solution_marked_{timestamp}.pdf"
    
    logger.info(f"  Processing paper PDF...")
    add_page_markers_to_pdf(paper_pdf, str(paper_marked_path), zero_based=True)
    logger.info(f"  ✓ Paper with markers: {paper_marked_path}")
    
    logger.info(f"  Processing solution PDF...")
    add_page_markers_to_pdf(solution_pdf, str(solution_marked_path), zero_based=True)
    logger.info(f"  ✓ Solution with markers: {solution_marked_path}")
    
    # Step 2: Upload marked PDFs
    logger.info("\n" + "="*80)
    logger.info("Step 2: Uploading marked PDFs to OpenAI...")
    logger.info("="*80)
    
    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    with open(paper_marked_path, 'rb') as f:
        paper_file = await openai_client.files.create(file=f, purpose="assistants")
    logger.info(f"  ✓ Paper file ID: {paper_file.id}")
    
    with open(solution_marked_path, 'rb') as f:
        solution_file = await openai_client.files.create(file=f, purpose="assistants")
    logger.info(f"  ✓ Solution file ID: {solution_file.id}")
    
    try:
        # Step 3: Process each test case
        logger.info("\n" + "="*80)
        logger.info("Step 3: Processing Test Cases (LaTeX Generation + Image Extraction)")
        logger.info("="*80)
        
        all_question_latex = []
        all_answer_latex = []
        all_results = []
        total_q_cost = 0.0
        total_a_cost = 0.0
        total_bbox_cost = 0.0
        
        for idx, test_case in enumerate(TEST_CASES, start=1):
            logger.info(f"\n{'='*80}")
            logger.info(f"Processing Test Case {idx}/{len(TEST_CASES)}: {test_case['question_label']}")
            logger.info(f"{'='*80}")
            logger.info(f"  Question Index: {test_case['question_index']}")
            logger.info(f"  Paper Pages: {test_case['paper_pages']}")
            logger.info(f"  Solution Pages: {test_case['solution_pages']}")
            
            try:
                # Generate LaTeX (concurrent)
                q_latex, a_latex, q_usage, a_usage = await generate_question_and_answer_latex_concurrent(
                    question_label=test_case['question_label'],
                    paper_pages=test_case['paper_pages'],
                    solution_pages=test_case['solution_pages'],
                    paper_file_id=paper_file.id,
                    solution_file_id=solution_file.id,
                    question_index=test_case['question_index']
                )
                
                q_cost = calculate_cost(q_usage.usage)
                a_cost = calculate_cost(a_usage.usage)
                total_q_cost += q_cost
                total_a_cost += a_cost
                
                logger.info(f"  ✓ LaTeX generated")
                logger.info(f"    Question: {len(q_latex.question_latex)} chars, {len(q_latex.question_images)} images")
                logger.info(f"    Answer: {len(a_latex.answer_latex)} chars, {len(a_latex.answer_images)} images, marks: {a_latex.marks}")
                
                # Step 4: Extract images from PDF
                logger.info(f"\n  Extracting images from PDF...")
                
                # Create images directory for this question
                images_dir = test_output_dir / "extracted_images" / f"question_{test_case['question_index']}"
                images_dir.mkdir(parents=True, exist_ok=True)
                
                # Extract question images
                if q_latex.question_images:
                    logger.info(f"    Extracting {len(q_latex.question_images)} question images...")
                    updated_q_images = extract_images_from_pdf(
                        pdf_path=paper_pdf,
                        images_info=q_latex.question_images,
                        output_dir=images_dir,
                        prefix=f"q{test_case['question_index']}_image"
                    )
                    # Update image paths to absolute paths for LaTeX export
                    for img in updated_q_images:
                        if img.image_path:
                            img.image_path = str(images_dir / img.image_path)
                    q_latex.question_images = updated_q_images
                    logger.info(f"    ✓ Extracted {len(updated_q_images)} question images")
                
                # Extract answer images
                if a_latex.answer_images:
                    logger.info(f"    Extracting {len(a_latex.answer_images)} answer images...")
                    updated_a_images = extract_images_from_pdf(
                        pdf_path=solution_pdf,
                        images_info=a_latex.answer_images,
                        output_dir=images_dir,
                        prefix=f"s{test_case['question_index']}_image"
                    )
                    # Update image paths to absolute paths for LaTeX export
                    for img in updated_a_images:
                        if img.image_path:
                            img.image_path = str(images_dir / img.image_path)
                    a_latex.answer_images = updated_a_images
                    logger.info(f"    ✓ Extracted {len(updated_a_images)} answer images")
                
                # Step 4.5: Correct image bboxes
                logger.info(f"\n  Correcting image bboxes...")
                question_bbox_cost = 0.0
                
                # Correct question images
                if q_latex.question_images:
                    logger.info(f"    Correcting {len(q_latex.question_images)} question image bboxes...")
                    corrected_q_images = []
                    for img_idx, img_info in enumerate(q_latex.question_images, start=1):
                        if img_info.image_path and Path(img_info.image_path).exists():
                            try:
                                logger.info(f"      Correcting question image {img_idx}/{len(q_latex.question_images)}...")
                                final_bbox, is_correct, bbox_usage, all_image_paths = await correct_image_bbox(
                                    question_label=test_case['question_label'],
                                    original_bbox=img_info.bbox,
                                    cropped_image_path=img_info.image_path,
                                    pdf_path=paper_pdf,
                                    page_number=img_info.page_number,
                                    expected_description=img_info.description or f"Question image {img_idx}",
                                    image_type="question",
                                    max_iterations=4
                                )
                                
                                bbox_cost = calculate_cost(bbox_usage)
                                question_bbox_cost += bbox_cost
                                
                                # Update image info with corrected bbox and final image path
                                updated_img = img_info.model_copy()
                                updated_img.bbox = final_bbox
                                updated_img.image_path = all_image_paths[-1]  # Use the final corrected image
                                corrected_q_images.append(updated_img)
                                
                                logger.info(f"      ✓ Question image {img_idx} corrected: is_correct={is_correct}")
                                logger.info(f"        Final bbox: {final_bbox}")
                                logger.info(f"        Cost: ${bbox_cost:.4f}")
                            except Exception as e:
                                logger.error(f"      ✗ Failed to correct question image {img_idx}: {e}")
                                corrected_q_images.append(img_info)  # Keep original if correction fails
                        else:
                            corrected_q_images.append(img_info)  # Keep original if no image path
                    
                    q_latex.question_images = corrected_q_images
                    logger.info(f"    ✓ Corrected {len(corrected_q_images)} question image bboxes")
                
                # Correct answer images
                if a_latex.answer_images:
                    logger.info(f"    Correcting {len(a_latex.answer_images)} answer image bboxes...")
                    corrected_a_images = []
                    for img_idx, img_info in enumerate(a_latex.answer_images, start=1):
                        if img_info.image_path and Path(img_info.image_path).exists():
                            try:
                                logger.info(f"      Correcting answer image {img_idx}/{len(a_latex.answer_images)}...")
                                final_bbox, is_correct, bbox_usage, all_image_paths = await correct_image_bbox(
                                    question_label=test_case['question_label'],
                                    original_bbox=img_info.bbox,
                                    cropped_image_path=img_info.image_path,
                                    pdf_path=solution_pdf,
                                    page_number=img_info.page_number,
                                    expected_description=img_info.description or f"Answer image {img_idx}",
                                    image_type="answer",
                                    max_iterations=4
                                )
                                
                                bbox_cost = calculate_cost(bbox_usage)
                                question_bbox_cost += bbox_cost
                                
                                # Update image info with corrected bbox and final image path
                                updated_img = img_info.model_copy()
                                updated_img.bbox = final_bbox
                                updated_img.image_path = all_image_paths[-1]  # Use the final corrected image
                                corrected_a_images.append(updated_img)
                                
                                logger.info(f"      ✓ Answer image {img_idx} corrected: is_correct={is_correct}")
                                logger.info(f"        Final bbox: {final_bbox}")
                                logger.info(f"        Cost: ${bbox_cost:.4f}")
                            except Exception as e:
                                logger.error(f"      ✗ Failed to correct answer image {img_idx}: {e}")
                                corrected_a_images.append(img_info)  # Keep original if correction fails
                        else:
                            corrected_a_images.append(img_info)  # Keep original if no image path
                    
                    a_latex.answer_images = corrected_a_images
                    logger.info(f"    ✓ Corrected {len(corrected_a_images)} answer image bboxes")
                
                logger.info(f"    Total bbox correction cost for this question: ${question_bbox_cost:.4f}")
                
                # Accumulate bbox cost to total
                total_bbox_cost += question_bbox_cost
                
                # Save individual question JSON
                safe_label = test_case['question_label'].replace('(', '').replace(')', '').replace(' ', '_')
                question_json_file = test_output_dir / f"question_{safe_label}.json"
                
                question_data = {
                    "metadata": {
                        "timestamp": datetime.now().isoformat(),
                        "model": settings.openai_model,
                        "question_index": test_case['question_index'],
                        "question_label": test_case['question_label'],
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
                    "page_info": {
                        "paper_pages": test_case['paper_pages'],
                        "solution_pages": test_case['solution_pages'],
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
                        "bbox_correction": {
                            "estimated_cost_usd": round(question_bbox_cost, 4)
                        },
                        "total": {
                            "duration_seconds": round(q_usage.duration_seconds + a_usage.duration_seconds, 2),
                            "total_tokens": q_usage.total_tokens + a_usage.total_tokens,
                            "estimated_cost_usd": round(q_cost + a_cost + question_bbox_cost, 4)
                        }
                    }
                }
                
                with open(question_json_file, 'w', encoding='utf-8') as f:
                    json.dump(question_data, f, indent=2, ensure_ascii=False)
                
                logger.info(f"  ✓ Saved to: {question_json_file}")
                
                # Add to results
                all_question_latex.append(q_latex)
                all_answer_latex.append(a_latex)
                all_results.append({
                    "question_index": test_case['question_index'],
                    "question_label": test_case['question_label'],
                    "paper_pages": test_case['paper_pages'],
                    "solution_pages": test_case['solution_pages'],
                    "usage": question_data["usage"]
                })
                
                
            except Exception as e:
                logger.error(f"  ✗ Failed to process {test_case['question_label']}: {e}")
                all_results.append({
                    "question_index": test_case['question_index'],
                    "question_label": test_case['question_label'],
                    "error": str(e)
                })
        
        # Step 5: Export to LaTeX folder structure
        logger.info(f"\n{'='*80}")
        logger.info(f"Step 5: Exporting to LaTeX Folder Structure")
        logger.info(f"{'='*80}")
        
        exporter = LatexExportUtility()
        exam_info = {
            'year': '2024',
            'school': 'Test',
            'grade': '12',
            'subject': 'Math',
            'task': 'Paper1_Questions_5_6'
        }
        
        latex_folder = exporter.export_latex_to_folder(
            question_latex_outputs=all_question_latex,
            answer_latex_outputs=all_answer_latex,
            output_dir=test_output_dir,
            exam_info=exam_info
        )
        
        logger.info(f"✓ LaTeX folder exported to: {latex_folder}")
        logger.info(f"  You can now compile paper.tex and solutions.tex")
        
        # Save complete results
        complete_result = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "model": settings.openai_model,
                "paper_pdf": paper_pdf,
                "solution_pdf": solution_pdf,
            },
            "test_cases": all_results,
            "summary": {
                "total_questions": len(TEST_CASES),
                "processed_questions": len([r for r in all_results if "error" not in r]),
                "failed_questions": len([r for r in all_results if "error" in r]),
                "total_costs": {
                    "question_latex": round(total_q_cost, 4),
                    "answer_latex": round(total_a_cost, 4),
                    "bbox_correction": round(total_bbox_cost, 4),
                    "total": round(total_q_cost + total_a_cost + total_bbox_cost, 4)
                }
            },
            "latex_folder": str(latex_folder)
        }
        
        result_file = test_output_dir / "complete_result.json"
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(complete_result, f, indent=2, ensure_ascii=False)
        
        logger.info(f"\n{'='*80}")
        logger.info(f"Complete Test Summary")
        logger.info(f"{'='*80}")
        logger.info(f"Total Questions: {len(TEST_CASES)}")
        logger.info(f"Processed: {len([r for r in all_results if 'error' not in r])}")
        logger.info(f"Failed: {len([r for r in all_results if 'error' in r])}")
        logger.info(f"")
        logger.info(f"Costs:")
        logger.info(f"  Question LaTeX: ${total_q_cost:.4f}")
        logger.info(f"  Answer LaTeX: ${total_a_cost:.4f}")
        logger.info(f"  Bbox Correction: ${total_bbox_cost:.4f}")
        logger.info(f"  Total: ${total_q_cost + total_a_cost + total_bbox_cost:.4f}")
        logger.info(f"")
        logger.info(f"✓ Complete results saved to: {result_file}")
        logger.info(f"✓ LaTeX folder: {latex_folder}")
        logger.info(f"✓ Individual question files saved to: {test_output_dir}")
        logger.info(f"{'='*80}")
        
    finally:
        # Clean up uploaded files
        await openai_client.files.delete(paper_file.id)
        await openai_client.files.delete(solution_file.id)
        logger.info("\n✓ Cleaned up uploaded files from OpenAI")
        
        # Clean up temporary marked PDFs
        if paper_marked_path.exists():
            paper_marked_path.unlink()
        if solution_marked_path.exists():
            solution_marked_path.unlink()
        logger.info("✓ Cleaned up temporary marked PDFs")


if __name__ == "__main__":
    asyncio.run(main())

