"""Pydantic data models for V4 workflow"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


# ============ 基础模型 ============

class ImageInfo(BaseModel):
    """图片信息"""
    model_config = ConfigDict(extra="forbid")
    
    page_number: int = Field(..., description="Page number where image appears")
    bbox: List[float] = Field(..., description="Bounding box [x1, y1, x2, y2]")
    description: Optional[str] = Field(None, description="Image description")
    image_path: Optional[str] = Field(None, description="Extracted image path")


class BboxCorrectionOutput(BaseModel):
    """Bbox 修正输出"""
    model_config = ConfigDict(extra="forbid")
    
    is_correct: bool = Field(..., description="Current crop is correct")
    confidence: float = Field(..., description="Confidence 0-1")
    issue_description: Optional[str] = Field(None, description="What's wrong with current crop")
    corrected_bbox: Optional[List[float]] = Field(None, description="Corrected bbox [x1,y1,x2,y2] if needed")
    reasoning: str = Field(..., description="Reasoning for decision")


# ============ 分类器输出 ============

class ExamTypeOutput(BaseModel):
    """试卷类型分类输出"""
    model_config = ConfigDict(extra="forbid")
    
    exam_type: Literal["type1", "type2"] = Field(
        ...,
        description="type1: separate answer booklet, type2: answer on paper"
    )
    reasoning: str = Field(..., description="Classification reasoning")
    confidence: Optional[float] = Field(None, description="Confidence score 0-1")


# ============ Question Lister输出 ============

class QuestionItem(BaseModel):
    """单个题目信息（来自Lister）"""
    model_config = ConfigDict(extra="forbid")
    
    question_index: int = Field(..., description="Sequential index (1-based)")
    question_label: str = Field(
        ...,
        description="Question label as it appears in paper (e.g., '10(a)', 'Question 21')"
    )


class QuestionList(BaseModel):
    """题目清单（Lister的输出）"""
    model_config = ConfigDict(extra="forbid")
    
    exam_type: str = Field(..., description="type1 or type2")
    total_questions: int = Field(..., description="Total number of questions")
    questions: List[QuestionItem] = Field(..., description="List of all questions")
    
    def validate_consistency(self) -> bool:
        """验证清单一致性"""
        return len(self.questions) == self.total_questions


# ============ Question Lister with Pages 输出 ============

class QuestionItemWithPages(BaseModel):
    """单个题目信息（包含页码位置，支持跨页）"""
    model_config = ConfigDict(extra="forbid")
    
    question_index: int = Field(..., description="Sequential index (1-based)")
    question_label: str = Field(
        ...,
        description="Question label as it appears in paper (e.g., '10(a)', 'Question 21')"
    )
    paper_pages: List[int] = Field(..., description="Page indices in paper PDF (0-based), may span multiple pages")
    solution_pages: List[int] = Field(..., description="Page indices in solution PDF (0-based), may span multiple pages")


class QuestionListWithPages(BaseModel):
    """题目清单（包含页码信息）"""
    model_config = ConfigDict(extra="forbid")
    
    exam_type: str = Field(..., description="type1 or type2")
    total_questions: int = Field(..., description="Total number of questions")
    questions: List[QuestionItemWithPages] = Field(..., description="List of all questions with page locations")
    
    def validate_consistency(self) -> bool:
        """验证清单一致性"""
        return len(self.questions) == self.total_questions


# ============ Question Processor输出 ============

class QuestionOutput(BaseModel):
    """单道题目的处理输出"""
    model_config = ConfigDict(extra="forbid")
    
    question_index: int = Field(..., description="Sequential index")
    question_number: str = Field(..., description="Question label like '10(a)'")
    
    question_latex: str = Field(..., description="Question LaTeX code")
    answer_latex: str = Field(..., description="Answer LaTeX code")
    
    question_images: List[ImageInfo] = Field(
        default_factory=list,
        description="Images in question"
    )
    answer_images: List[ImageInfo] = Field(
        default_factory=list,
        description="Images in answer"
    )
    
    marks: Optional[int] = Field(None, description="Question marks")
    reasoning: Optional[str] = Field(None, description="Processing reasoning")


# ============ 最终输出 ============

class ProcessedExam(BaseModel):
    """完整试卷处理结果"""
    model_config = ConfigDict(extra="forbid")
    
    exam_id: str = Field(..., description="Exam ID")
    exam_type: str = Field(..., description="type1 or type2")
    
    total_questions: int = Field(..., description="Total questions")
    questions: List[QuestionOutput] = Field(..., description="All processed questions")
    
    # 文件信息
    paper_pdf_path: str = Field(..., description="Original paper PDF path")
    solution_pdf_path: str = Field(..., description="Original solution PDF path")
    paper_file_id: Optional[str] = Field(None, description="OpenAI paper file ID")
    solution_file_id: Optional[str] = Field(None, description="OpenAI solution file ID")
    
    # 元数据
    processing_time_seconds: Optional[float] = Field(None, description="Total processing time")
    workflow_version: str = Field(default="v4_file_based", description="Workflow version")


# ============ LaTeX Generator 输出 ============

class QuestionLatexOutput(BaseModel):
    """题目 LaTeX 生成输出"""
    model_config = ConfigDict(extra="forbid")
    
    question_label: str = Field(..., description="Question label")
    question_latex: str = Field(..., description="Generated LaTeX code")
    question_images: List[ImageInfo] = Field(
        default_factory=list,
        description="Images in question with positions"
    )
    compilation_success: bool = Field(default=True, description="LaTeX compilation status")
    error_message: Optional[str] = Field(None, description="Error if compilation failed")


class AnswerLatexOutput(BaseModel):
    """答案 LaTeX 生成输出"""
    model_config = ConfigDict(extra="forbid")
    
    question_label: str = Field(..., description="Question label")
    answer_latex: str = Field(..., description="Generated LaTeX code")
    answer_images: List[ImageInfo] = Field(
        default_factory=list,
        description="Images in answer with positions"
    )
    marks: Optional[int] = Field(None, description="Marks for this question")
    compilation_success: bool = Field(default=True, description="LaTeX compilation status")
    error_message: Optional[str] = Field(None, description="Error if compilation failed")


# ============ Labelling Agent 输出 ============

class QuestionLabelOutput(BaseModel):
    """题目标注输出"""
    model_config = ConfigDict(extra="forbid")
    
    question_index: int = Field(..., description="Question index (sequential number)")
    question_label: str = Field(..., description="Question label")
    topic_id: int = Field(..., description="Topic ID")
    subtopic_id: int = Field(..., description="Subtopic ID (most important, must be accurate)")
    question_type: Literal["short answer", "multiple choice"] = Field(
        ...,
        description="Question type: must be either 'short answer' or 'multiple choice'"
    )
    difficulty: Optional[str] = Field(None, description="Difficulty level (e.g., 'Easy', 'Medium', 'Hard')")
    mark: Optional[int] = Field(None, description="Marks for this question")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence score 0-1")
    reasoning: str = Field(..., description="Detailed reasoning for the labelling decision")

