"""Complete Test Workflow for Import V4 - From Classification to Labelling All Questions"""

import asyncio
import sys
from src.services.services_v2.import_paper.import_v4.workflow import run_complete_workflow
from src.logger import logger


async def main():
    if len(sys.argv) < 5:
        print("Usage: python -m src.services.services_v2.import_paper.import_v4.test_latex_generator <paper_pdf> <solution_pdf> <subject_id> <grade_id>")
        print("\nThis script runs the complete workflow:")
        print("  1. Classification (exam type)")
        print("  2. Question Lister (list all questions)")
        print("  3. For each question:")
        print("     - Generate Question LaTeX")
        print("     - Generate Answer LaTeX")
        print("     - Label question (topic, subtopic, type, difficulty, mark)")
        sys.exit(1)
    
    paper_pdf = sys.argv[1]
    solution_pdf = sys.argv[2]
    subject_id = int(sys.argv[3])
    grade_id = int(sys.argv[4])
    
    logger.info(f"="*80)
    logger.info(f"Complete Import V4 Test Workflow")
    logger.info(f"="*80)
    logger.info(f"Paper PDF: {paper_pdf}")
    logger.info(f"Solution PDF: {solution_pdf}")
    logger.info(f"Subject ID: {subject_id}, Grade ID: {grade_id}")
    logger.info(f"="*80)
    
    # Run complete workflow
    result = await run_complete_workflow(
        paper_pdf_path=paper_pdf,
        solution_pdf_path=solution_pdf,
        subject_id=subject_id,
        grade_id=grade_id,
        exam_id=None,  # Will be auto-generated
        output_dir=None  # Will use default output directory
    )
    
    logger.info(f"\n✓ Complete workflow finished!")
    logger.info(f"  Output directory: {result['output_dir']}")
    logger.info(f"  Total questions: {result['question_list'].total_questions}")
    logger.info(f"  Total cost: ${result['api_usage']['total_cost']:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
