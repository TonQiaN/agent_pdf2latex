"""Agents module - Import Paper V4 Workflow Agents

Workflow Order:
0. Classifier Agent - Classifies exam type (type1/type2)
1. Question Lister Agent - Lists all questions and their page locations
2. Question LaTeX Agent - Generates LaTeX for individual questions
3. Answer LaTeX Agent - Generates LaTeX for individual answers
3.5. Concurrent LaTeX Agent - Concurrent generation of question and answer LaTeX
4. Image Bbox Corrector Agent - Verifies and corrects image bounding boxes
5. Labelling Agent - Labels questions with topic, subtopic, type, difficulty, and mark
"""

from dataclasses import dataclass
from agents import Usage


@dataclass
class UsageWithDuration:
    """Usage statistics with execution duration"""
    usage: Usage
    duration_seconds: float
    
    @property
    def requests(self):
        return self.usage.requests
    
    @property
    def input_tokens(self):
        return self.usage.input_tokens
    
    @property
    def output_tokens(self):
        return self.usage.output_tokens
    
    @property
    def total_tokens(self):
        return self.usage.total_tokens


from ._0_classifier_agent import classify_exam_type_direct
from ._1_question_lister_agent import (
    list_all_questions_with_pages_direct,
    annotate_paper_pages,
    annotate_solution_pages,
)
from ._2_question_latex_agent import generate_question_latex_direct
from ._3_answer_latex_agent import generate_answer_latex_direct
from ._3dot5_concurrent_latex_agent import generate_question_and_answer_latex_concurrent
from ._4_image_bbox_corrector_agent import correct_image_bbox
from ._5_labelling_agent import label_question_direct


__all__ = [
    "UsageWithDuration",
    "classify_exam_type_direct",
    "list_all_questions_with_pages_direct",
    "annotate_paper_pages",
    "annotate_solution_pages",
    "generate_question_latex_direct",
    "generate_answer_latex_direct",
    "generate_question_and_answer_latex_concurrent",
    "correct_image_bbox",
    "label_question_direct",
]

