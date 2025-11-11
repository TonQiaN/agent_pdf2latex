"""
LaTeX Export Utility for import_v4

Exports question and answer LaTeX outputs to structured folder format
compatible with latex_validation system.
"""

import shutil
from pathlib import Path
from typing import List, Dict, Optional
from loguru import logger

from ..models.schemas import QuestionLatexOutput, AnswerLatexOutput, ImageInfo
from src.configurations import PathConfig


class LatexExportUtility:
    """
    Utility for exporting LaTeX generation results to folder structure
    
    Creates folder structure similar to latex_validation:
    - questions/Q*.tex - Individual question files
    - solutions/S*.tex - Individual solution files
    - Figures/ - Image files
    - templates/ - LaTeX templates
    - paper.tex - Main question wrapper
    - solutions.tex - Main solution wrapper
    """
    
    def __init__(self):
        """Initialize LaTeX export utility"""
        logger.info("LatexExportUtility initialized")
    
    def export_latex_to_folder(
        self,
        question_latex_outputs: List[QuestionLatexOutput],
        answer_latex_outputs: List[AnswerLatexOutput],
        output_dir: Path,
        exam_info: Dict[str, str]
    ) -> Path:
        """
        Export LaTeX outputs to structured folder
        
        Args:
            question_latex_outputs: List of question LaTeX outputs
            answer_latex_outputs: List of answer LaTeX outputs
            output_dir: Base output directory
            exam_info: Dict containing year, school, grade, subject, task
            
        Returns:
            Path to the created folder
            
        Raises:
            ValueError: If inputs don't match or are invalid
            Exception: For other errors
        """
        try:
            # Validate inputs
            if len(question_latex_outputs) != len(answer_latex_outputs):
                raise ValueError(
                    f"Question count ({len(question_latex_outputs)}) must match "
                    f"answer count ({len(answer_latex_outputs)})"
                )
            
            # Extract exam info
            year = exam_info.get('year', '2024')
            school = exam_info.get('school', 'Unknown')
            grade = exam_info.get('grade', '12')
            subject = exam_info.get('subject', 'Math')
            task = exam_info.get('task', 'Paper1')
            
            logger.info(f"Exporting {len(question_latex_outputs)} questions to LaTeX folder")
            
            # Create folder structure
            folder_name = f"{year}_{school}_{grade}_{subject}_{task}_LaTeX"
            paper_folder = Path(output_dir) / folder_name
            
            # Create subfolders
            figures_folder = paper_folder / "Figures"
            questions_folder = paper_folder / "questions"
            solutions_folder = paper_folder / "solutions"
            
            paper_folder.mkdir(parents=True, exist_ok=True)
            figures_folder.mkdir(exist_ok=True)
            questions_folder.mkdir(exist_ok=True)
            solutions_folder.mkdir(exist_ok=True)
            
            logger.info(f"Created folder structure at: {paper_folder}")
            
            # Copy templates and watermarks from assets
            materials_dir = PathConfig.assets
            
            templates_src = materials_dir / "templates"
            if templates_src.exists():
                shutil.copytree(
                    templates_src,
                    paper_folder / "templates",
                    dirs_exist_ok=True
                )
                logger.info("Copied templates")
            else:
                logger.warning(f"Templates not found at {templates_src}")
            
            watermarks_src = materials_dir / "watermarks"
            if watermarks_src.exists():
                shutil.copytree(
                    watermarks_src,
                    figures_folder / "watermarks",
                    dirs_exist_ok=True
                )
                logger.info("Copied watermarks")
            else:
                logger.warning(f"Watermarks not found at {watermarks_src}")
            
            # Track tex inputs for main files
            all_question_tex = []
            all_solution_tex = []
            
            # Process each question/answer pair
            for idx, (q_latex, a_latex) in enumerate(
                zip(question_latex_outputs, answer_latex_outputs), 
                start=1
            ):
                # Extract question_index from question_label if available
                # Try to extract number from label (e.g., "Question 5" -> 5)
                question_index = None
                import re
                match = re.search(r'\d+', q_latex.question_label)
                if match:
                    question_index = int(match.group())
                
                # Write question tex file
                question_file = questions_folder / f"Q{idx}.tex"
                question_file.write_text(q_latex.question_latex, encoding="utf-8")
                all_question_tex.append(f"\\input{{questions/Q{idx}.tex}}")
                
                # Write solution tex file
                solution_file = solutions_folder / f"S{idx}.tex"
                solution_file.write_text(a_latex.answer_latex, encoding="utf-8")
                all_solution_tex.append(f"\\input{{solutions/S{idx}.tex}}")
                
                # Save question images with placeholder format
                if q_latex.question_images:
                    self._save_images(
                        q_latex.question_images,
                        figures_folder,
                        question_index=question_index,
                        image_type="question"
                    )
                
                # Save answer images with placeholder format
                if a_latex.answer_images:
                    self._save_images(
                        a_latex.answer_images,
                        figures_folder,
                        question_index=question_index,
                        image_type="solution"
                    )
            
            logger.info(f"Wrote {len(all_question_tex)} question and solution files")
            
            # Generate paper.tex
            paper_tex_content = [
                "\\documentclass[twocolumn]{article}",
                "\\input{templates/paper_template}",
                "",
                "\\begin{document}",
                "\\onecolumn",
                "\\section*{Question}",
                "\\begin{enumerate}[label=Q\\arabic*:]"
            ]
            paper_tex_content.extend(all_question_tex)
            paper_tex_content.append("\\end{enumerate}")
            paper_tex_content.append("")
            paper_tex_content.append("\\end{document}")
            
            (paper_folder / "paper.tex").write_text(
                "\n\n".join(paper_tex_content),
                encoding="utf-8"
            )
            logger.info("Generated paper.tex")
            
            # Generate solutions.tex
            solutions_tex_content = [
                "\\documentclass[twocolumn]{article}",
                "\\input{templates/solution_template}",
                "",
                "\\begin{document}",
                "\\section*{Solution}",
                "\\begin{enumerate}[label=Q\\arabic*:]"
            ]
            solutions_tex_content.extend(all_solution_tex)
            solutions_tex_content.append("\\end{enumerate}")
            solutions_tex_content.append("")
            solutions_tex_content.append("\\end{document}")
            
            (paper_folder / "solutions.tex").write_text(
                "\n\n".join(solutions_tex_content),
                encoding="utf-8"
            )
            logger.info("Generated solutions.tex")
            
            logger.info(f"✓ Successfully exported LaTeX folder to: {paper_folder}")
            
            return paper_folder
            
        except Exception as e:
            logger.error(f"Error exporting LaTeX folder: {e}", exc_info=True)
            raise
    
    def _save_images(
        self,
        images: List[ImageInfo],
        figures_dir: Path,
        question_index: Optional[int] = None,
        image_type: str = "question"
    ):
        """
        Save images to Figures folder with placeholder format
        
        Args:
            images: List of ImageInfo objects
            figures_dir: Figures directory path
            question_index: Question index for placeholder format (e.g., 5 for "Question 5")
            image_type: Image type ("question" or "solution")
        """
        for idx, img_info in enumerate(images, 1):
            if img_info.image_path:
                # If image was already extracted, copy it
                src = Path(img_info.image_path)
                if src.exists():
                    # Use placeholder format: idPLACEHOLDER{question_index}_{index}.png
                    # or idPLACEHOLDER{question_index}_sol_{index}.png for solutions
                    if question_index is not None:
                        if image_type == "solution":
                            dst_filename = f"idPLACEHOLDER{question_index}_sol_{idx}.png"
                        else:
                            dst_filename = f"idPLACEHOLDER{question_index}_{idx}.png"
                    else:
                        # Fallback to old format if question_index not available
                        dst_filename = f"{image_type}_{idx}.png"
                    
                    dst = figures_dir / dst_filename
                    shutil.copy(src, dst)
                    logger.debug(f"Copied image: {src.name} -> {dst.name}")
                else:
                    logger.warning(f"Image file not found: {src}")
            else:
                logger.debug(f"No image path for {image_type} image {idx}")


class LatexExportError(Exception):
    """Custom exception for export errors"""
    pass

