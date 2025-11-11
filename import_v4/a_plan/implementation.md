# V3 File-Based Workflow - 实现细节

## 目录结构

```
import_v4/
├── __init__.py
├── main.py                          # 主入口（仅调用workflow）
├── workflow.py                      # 🆕 完整工作流逻辑
├── config/
│   ├── __init__.py
│   └── settings.py                  # 配置管理
├── models/
│   ├── __init__.py
│   └── schemas.py                   # Pydantic数据模型
├── preprocessing/
│   ├── __init__.py
│   └── pdf_renderer.py              # PDF预处理和渲染
├── services/
│   ├── __init__.py
│   └── file_uploader.py             # 🆕 OpenAI文件上传服务
├── agents/
│   ├── __init__.py
│   ├── classifier_agent.py          # 试卷类型分类器
│   ├── question_lister_agent.py     # 🆕 题目清单Agent
│   ├── file_based_question_processor.py  # 🆕 基于File ID的题目处理Agent
│   ├── prompts.py                   # Agent提示词
│   ├── file_lister_prompts.py       # 🆕 Lister专用提示词
│   ├── file_processor_prompts.py    # 🆕 File Processor专用提示词
│   └── safety_controller.py         # 安全控制器
├── tools/
│   ├── __init__.py
│   └── latex_compiler.py            # LaTeX编译工具
├── postprocessing/
│   ├── __init__.py
│   ├── image_extractor.py           # 图片提取
│   └── metadata_extractor.py        # 元数据提取
└── utils/
    ├── __init__.py
    └── logger.py                    # 日志配置
```

---

## 详细实现

### 1. 配置管理 (`config/settings.py`)

```python
"""Configuration settings for import_v4"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings"""
    
    # OpenAI配置
    openai_api_key: str
    openai_model: str = "gpt-4o"  # 默认模型
    
    # Agent配置
    max_turns_per_question: int = 15
    max_latex_fix_attempts: int = 2
    
    # 文件上传配置
    file_upload_purpose: str = "assistants"
    auto_cleanup_files: bool = False  # 是否自动清理上传的文件
    
    # 分类器配置
    classifier_max_turns: int = 5
    classification_sample_pages: int = 3  # 用于分类的页面数量（取倒数第2、4、6页，或最后3页）
    
    # Lister配置
    lister_max_turns: int = 10
    
    # 输出配置
    output_dir: str = "output"
    save_question_list: bool = True  # 是否保存题目清单
    
    class Config:
        env_file = ".env"
        env_prefix = "EXAM_PROCESSOR_"


settings = Settings()
```

---

### 2. 数据模型 (`models/schemas.py`)

```python
"""Pydantic data models for V3 workflow"""

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
    workflow_version: str = Field(default="v3_file_based", description="Workflow version")
```

---

### 3. 文件上传服务 (`services/file_uploader.py`) 🆕

```python
"""File uploader service for OpenAI"""

from pathlib import Path
from typing import Dict, Optional
from openai import AsyncOpenAI
from loguru import logger

from ..config.settings import settings


class FileUploadResult:
    """文件上传结果"""
    def __init__(
        self,
        paper_file_id: str,
        solution_file_id: str,
        paper_file,
        solution_file
    ):
        self.paper_file_id = paper_file_id
        self.solution_file_id = solution_file_id
        self.paper_file = paper_file
        self.solution_file = solution_file
    
    def to_dict(self) -> Dict[str, str]:
        return {
            "paper_file_id": self.paper_file_id,
            "solution_file_id": self.solution_file_id
        }


async def upload_pdfs_get_file_ids(
    paper_pdf_path: str,
    solution_pdf_path: str,
    client: Optional[AsyncOpenAI] = None
) -> FileUploadResult:
    """
    上传PDF到OpenAI，获取持久化file_id
    
    Args:
        paper_pdf_path: Paper PDF路径
        solution_pdf_path: Solution PDF路径
        client: 可选的OpenAI客户端（用于复用连接）
    
    Returns:
        FileUploadResult: 包含file_id的结果对象
    
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
    
    logger.info("📤 Uploading paper PDF to OpenAI...")
    logger.info(f"   File: {paper_path.name} ({paper_path.stat().st_size / 1024:.1f} KB)")
    
    try:
        with open(paper_pdf_path, 'rb') as f:
            paper_file = await client.files.create(
                file=f,
                purpose=settings.file_upload_purpose
            )
        logger.info(f"✓ Paper uploaded: {paper_file.id}")
    except Exception as e:
        logger.error(f"Failed to upload paper PDF: {e}")
        raise
    
    logger.info("📤 Uploading solution PDF to OpenAI...")
    logger.info(f"   File: {solution_path.name} ({solution_path.stat().st_size / 1024:.1f} KB)")
    
    try:
        with open(solution_pdf_path, 'rb') as f:
            solution_file = await client.files.create(
                file=f,
                purpose=settings.file_upload_purpose
            )
        logger.info(f"✓ Solution uploaded: {solution_file.id}")
    except Exception as e:
        logger.error(f"Failed to upload solution PDF: {e}")
        # 清理已上传的paper文件
        try:
            await client.files.delete(paper_file.id)
            logger.info(f"✓ Cleaned up paper file: {paper_file.id}")
        except:
            pass
        raise
    
    return FileUploadResult(
        paper_file_id=paper_file.id,
        solution_file_id=solution_file.id,
        paper_file=paper_file,
        solution_file=solution_file
    )


async def cleanup_files(
    file_ids: list[str],
    client: Optional[AsyncOpenAI] = None
):
    """
    清理上传的文件
    
    Args:
        file_ids: 文件ID列表
        client: 可选的OpenAI客户端
    """
    if client is None:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    logger.info(f"🧹 Cleaning up {len(file_ids)} files...")
    
    for file_id in file_ids:
        try:
            await client.files.delete(file_id)
            logger.info(f"✓ File deleted: {file_id}")
        except Exception as e:
            logger.warning(f"Failed to delete file {file_id}: {e}")


async def verify_file_exists(
    file_id: str,
    client: Optional[AsyncOpenAI] = None
) -> bool:
    """
    验证文件是否存在于OpenAI
    
    Args:
        file_id: 文件ID
        client: 可选的OpenAI客户端
    
    Returns:
        True if file exists, False otherwise
    """
    if client is None:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    try:
        file_info = await client.files.retrieve(file_id)
        logger.info(f"✓ File exists: {file_id} ({file_info.filename})")
        return True
    except Exception as e:
        logger.warning(f"File not found: {file_id} ({e})")
        return False
```

---

### 4. 轻量级预处理 (`preprocessing/pdf_renderer.py`)

在现有代码基础上添加新函数：

```python
"""PDF rendering and preprocessing"""

import fitz  # PyMuPDF
from typing import Dict, List
from loguru import logger


async def preprocess_for_classification(paper_pdf_path: str) -> Dict:
    """
    轻量级预处理：渲染指定页面用于分类
    
    策略（与 import_v3 一致）：
    - 优先使用倒数第 2、4、6 页
    - 如果页数不足，使用最后 N 页
    
    Args:
        paper_pdf_path: Paper PDF路径
    
    Returns:
        {
            "selected_pages": [page1_data, page2_data, ...],
            "paper_pdf_path": str,
            "total_pages": int
        }
    """
    from ..config.settings import settings
    import base64
    
    logger.info(f"📄 Preprocessing for classification...")
    
    doc = fitz.open(paper_pdf_path)
    total_pages = len(doc)
    
    logger.info(f"   Total pages: {total_pages}")
    
    # 选择页面：优先使用倒数第 2、4、6 页
    target_indices = []
    for offset in [2, 4, 6]:
        idx = total_pages - offset
        if idx >= 0:
            target_indices.append(idx)
    
    # 如果页数不足，使用最后 N 页
    if len(target_indices) < settings.classification_sample_pages:
        target_indices = list(range(
            max(0, total_pages - settings.classification_sample_pages), 
            total_pages
        ))
    
    # 排序以保持页面顺序
    target_indices.sort()
    
    # 页码（1-based）
    page_numbers = [idx + 1 for idx in target_indices]
    logger.info(f"   Selected pages for classification: {page_numbers}")
    
    # 渲染选中的页面
    selected_pages = []
    for idx in target_indices:
        page_num = idx + 1
        logger.info(f"   Rendering page {page_num}...")
        page = doc[idx]
        
        # 渲染为图片
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x scale
        img_bytes = pix.tobytes("png")
        
        # Base64编码
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
        
        page_data = {
            "page_number": page_num,
            "image_base64": img_base64,
            "width": pix.width,
            "height": pix.height
        }
        selected_pages.append(page_data)
    
    doc.close()
    
    logger.info(f"✓ Preprocessed {len(selected_pages)} pages for classification")
    
    return {
        "selected_pages": selected_pages,
        "paper_pdf_path": paper_pdf_path,
        "total_pages": total_pages
    }


# 现有的preprocess_pdfs函数保持不变（用于其他模式）
```

---

### 5. 试卷类型分类器 (`agents/classifier_agent.py`)

```python
"""Exam Type Classifier Agent"""

from loguru import logger
from agents import Agent, Runner

from ..config.settings import settings
from ..models.schemas import ExamTypeOutput


async def classify_exam_type(classification_data: dict) -> str:
    """
    使用选定的页面进行试卷类型分类
    
    策略（与 import_v3 一致）：
    - 使用倒数第 2、4、6 页（或最后 N 页）
    - 这些页面通常包含答题区域，更容易判断试卷类型
    
    Args:
        classification_data: 预处理数据，包含 selected_pages
    
    Returns:
        试卷类型字符串: "type1" or "type2"
    """
    from .prompts import get_classifier_prompt
    
    classifier_agent = Agent(
        name="Exam Classifier",
        instructions=get_classifier_prompt(),
        output_type=ExamTypeOutput,
        model=settings.openai_model
    )
    
    selected_pages = classification_data["selected_pages"]
    page_numbers = [p["page_number"] for p in selected_pages]
    
    logger.info(f"📊 Classifying exam type using pages: {page_numbers}")
    
    # 构建输入，包含实际的 base64 图片
    input_text = "Analyze these pages to determine exam type:\n\n"
    for page in selected_pages:
        image_marker = f"[IMAGE:data:image/png;base64,{page['image_base64']}]"
        input_text += f"Page {page['page_number']}:\n{image_marker}\n\n"
    
    # 执行分类
    result = await Runner.run(
        classifier_agent,
        input=input_text,
        max_turns=settings.classifier_max_turns
    )
    
    exam_type_output = result.final_output
    
    logger.info(f"✓ Classification result: {exam_type_output.exam_type}")
    logger.info(f"   Reasoning: {exam_type_output.reasoning}")
    if exam_type_output.confidence:
        logger.info(f"   Confidence: {exam_type_output.confidence:.2f}")
    
    return exam_type_output.exam_type


def get_classifier_prompt() -> str:
    """
    分类器提示词（与 import_v3 一致）
    """
    return """Analyze the provided pages of this exam and determine its type.

**Type1** (Separate Answer Booklet):
- Explicitly states "Use a SEPARATE writing booklet" or similar
- No blank lines or answer spaces under questions
- Questions are densely packed
- Example: "10(a)", "10(b)", "10(c)" are independent questions

**Type2** (Answer on Paper):
- Has blank lines with underscores (______) under questions
- Clear answer spaces between questions
- Questions have more spacing
- Example: "Question 21" is one complete question with sub-parts (a), (b), (c)

**Analysis Guidelines**:
1. Look for explicit instructions about where to write answers
2. Check for blank answer spaces or lines
3. Observe question density and spacing
4. Note the question numbering pattern

Return JSON with:
{
    "exam_type": "type1" or "type2",
    "reasoning": "Detailed explanation of classification decision",
    "confidence": 0.0-1.0 (optional)
}

**Important**: Base your decision on multiple indicators, not just one feature.
"""
```

---

### 6. Question Lister Agent (`agents/question_lister_agent.py`) 🆕

```python
"""Question Lister Agent - List all questions from paper PDF"""

from typing import List
from loguru import logger
from agents import Agent, Runner, FileSearchTool

from ..config.settings import settings
from ..models.schemas import QuestionList, QuestionItem


def get_question_lister_prompt(exam_type: str) -> str:
    """
    生成Question Lister的prompt
    
    Args:
        exam_type: "type1" or "type2"
    
    Returns:
        Prompt string
    """
    if exam_type == "type1":
        cutting_rule = """
【Type1 Rules】(Separate Answer Booklet):
- Question 10 is a **section title**, not an independent question
- 10(a), 10(b), 10(c) are **independent questions** (minimum splitting unit)
- 10(c)(i), 10(c)(ii) are **sub-parts** of 10(c), NOT separate questions
- Recognition pattern: ^\\d+\\([a-z]\\)$ indicates start of independent question

Example:
  10          ← Section title, NOT a question
  10(a)       ← Question 1: "10(a)"
  10(b)       ← Question 2: "10(b)"
  10(c)       ← Question 3: "10(c)"
    (i)       ← Sub-part of 10(c), NOT separate
    (ii)      ← Sub-part of 10(c), NOT separate
  11(a)       ← Question 4: "11(a)"
"""
    else:
        cutting_rule = """
【Type2 Rules】(Answer on Paper):
- "Question 21" is **one complete question** (minimum splitting unit)
- 21(a), 21(b), 21(c) are **sub-parts**, NOT separate questions
- Recognition pattern: ^Question \\d+$ indicates start of question

Example:
  Question 21    ← Question 1: "Question 21"
    (a)          ← Sub-part, NOT separate
    (b)          ← Sub-part, NOT separate
  Question 22    ← Question 2: "Question 22"
    (a)          ← Sub-part, NOT separate
"""
    
    return f"""You are a Question Lister Agent. Your task is to scan the entire paper PDF and create a **complete, accurate list** of all questions.

=== Exam Type ===
{exam_type}

=== Question Splitting Rules ===
{cutting_rule}

=== Your Task ===
1. Use the FileSearchTool to systematically scan the entire paper PDF
2. Identify ALL questions in the document
3. For each question, record:
   - question_index: Sequential number starting from 1 (1, 2, 3, ...)
   - question_label: **Exact label** as it appears in the paper (e.g., "10(a)", "Question 21")

=== Search Strategy ===
- Start from the beginning of the document
- Search for question patterns systematically
- Don't skip any sections
- Verify you've reached the end of the exam
- Double-check the count

=== Critical Rules ===
✅ DO:
- Follow the splitting rules **strictly**
- Preserve exact question labels (including parentheses, capitalization)
- Number questions sequentially (1, 2, 3, ...)
- Include ALL questions, no matter how short

❌ DON'T:
- Split sub-parts into separate questions
- Guess or skip questions
- Change the question labels
- Include section titles as questions (for type1)

=== Output Format ===
Return a QuestionList with:
{{
    "exam_type": "{exam_type}",
    "total_questions": <count>,
    "questions": [
        {{"question_index": 1, "question_label": "..."}},
        {{"question_index": 2, "question_label": "..."}},
        ...
    ]
}}

=== Quality Check ===
Before returning, verify:
1. total_questions == len(questions)
2. question_index are sequential (1, 2, 3, ...)
3. No duplicate question_labels
4. All question_labels follow the format rules

Begin scanning now using the FileSearchTool. Be thorough and accurate!
"""


async def list_all_questions(
    exam_type: str,
    paper_file_id: str
) -> QuestionList:
    """
    列出paper中的所有题目
    
    Args:
        exam_type: 试卷类型 ("type1" or "type2")
        paper_file_id: 已上传的paper file ID
    
    Returns:
        QuestionList: 包含所有题目的清单
    
    Raises:
        Exception: 如果Agent执行失败
    """
    logger.info(f"📋 Listing all questions from paper...")
    logger.info(f"   Exam type: {exam_type}")
    logger.info(f"   Paper file ID: {paper_file_id}")
    
    # 创建FileSearchTool
    file_search = FileSearchTool(file_ids=[paper_file_id])
    
    # 创建Agent
    lister_agent = Agent(
        name="Question Lister",
        instructions=get_question_lister_prompt(exam_type),
        tools=[file_search],
        output_type=QuestionList,
        model=settings.openai_model
    )
    
    # 执行
    try:
        result = await Runner.run(
            lister_agent,
            input="List all questions from the paper PDF. Be systematic and thorough.",
            max_turns=settings.lister_max_turns
        )
        
        question_list = result.final_output
        
        # 验证一致性
        if not question_list.validate_consistency():
            logger.warning(
                f"⚠️  Inconsistency detected: total_questions={question_list.total_questions}, "
                f"actual count={len(question_list.questions)}"
            )
        
        logger.info(f"✓ Found {question_list.total_questions} questions")
        
        # 显示前几道题
        preview_count = min(5, len(question_list.questions))
        for q in question_list.questions[:preview_count]:
            logger.info(f"  [{q.question_index}] {q.question_label}")
        
        if question_list.total_questions > preview_count:
            logger.info(f"  ... and {question_list.total_questions - preview_count} more")
        
        return question_list
        
    except Exception as e:
        logger.error(f"Failed to list questions: {e}")
        logger.exception(e)
        raise
```

---

### 7. File-Based Question Processor (`agents/file_based_question_processor.py`) 🆕

```python
"""File-Based Question Processor - Process questions using file IDs"""

from typing import List, Optional
from loguru import logger
from agents import Agent, Runner, FileSearchTool

from ..config.settings import settings
from ..models.schemas import QuestionOutput, QuestionList
from ..tools.latex_compiler import compile_latex
from .safety_controller import safety_controller


def get_file_based_processor_prompt(
    exam_type: str,
    question_label: str
) -> str:
    """
    生成基于file_id的Question Processor prompt
    
    Args:
        exam_type: "type1" or "type2"
        question_label: 题目标签 (如 "10(a)", "Question 21")
    
    Returns:
        Prompt string
    """
    if exam_type == "type1":
        content_rule = "Keep all sub-parts (i), (ii), (iii) in the question/answer content"
    else:
        content_rule = "Keep all sub-parts (a), (b), (c) in the question/answer content"
    
    return f"""You are a Question Processor Agent. Your task is to extract and process question **{question_label}** from the PDFs.

=== Target Question ===
{question_label}

=== Available Resources ===
You have access to two PDF files via FileSearchTool:
1. **Paper PDF** - contains the question text
2. **Solution PDF** - contains the answer

=== Processing Workflow ===

**Step 1: Find the Question** 🔍
- Use FileSearchTool to search for "{question_label}" in the paper
- Read the **complete** question text
- Important: The question may span multiple pages
- Include ALL content until the next question starts

**Step 2: Find the Answer** 🔍
- Use FileSearchTool to search for the answer to "{question_label}" in the solution
- Read the **complete** answer text
- Important: The answer may span multiple pages
- Include ALL content until the next answer starts

**Step 3: Generate LaTeX** ✍️
- Convert question text to `question_latex`
- Convert answer text to `answer_latex`
- Rules:
  - {content_rule}
  - Use proper LaTeX formatting
  - Preserve mathematical notation
  - Use \\textbf, \\textit for emphasis
  - Use \\begin{{enumerate}}, \\begin{{itemize}} for lists

**Step 4: Identify Images** 🖼️
- Mark approximate locations of all images
- For each image provide:
  - page_number: which page the image appears on
  - bbox: [x1, y1, x2, y2] in PDF coordinates (origin at top-left)
  - description: brief description of the image

**Step 5: Extract Marks** 🎯
- Look for marks notation like [5], [8 marks], etc.
- Extract the numeric value

**Step 6: Verify LaTeX** ✅
- Call compile_latex(question_latex, "question") to verify
- Call compile_latex(answer_latex, "answer") to verify
- If compilation fails:
  - Analyze the error message
  - Fix the LaTeX syntax
  - Retry compilation (max {settings.max_latex_fix_attempts} attempts)

=== Output Format ===
Return a QuestionOutput with:
{{
    "question_index": <will be set externally>,
    "question_number": "{question_label}",
    "question_latex": "...",
    "answer_latex": "...",
    "question_images": [...],
    "answer_images": [...],
    "marks": <number or null>,
    "reasoning": "Brief explanation of your process"
}}

=== Important Notes ===
- **Be thorough**: Extract ALL content, don't truncate
- **Use FileSearchTool**: Don't guess, always search
- **Multi-page handling**: If content spans pages, search multiple times
- **Image bbox**: Estimate as best as you can, format [x1, y1, x2, y2]
- **LaTeX quality**: Ensure it compiles successfully

Begin processing question {question_label} now.
"""


async def process_question_from_files(
    question_index: int,
    question_label: str,
    paper_file_id: str,
    solution_file_id: str,
    exam_type: str
) -> QuestionOutput:
    """
    从file_id处理单道题目
    
    Args:
        question_index: 题目序号 (1-based)
        question_label: 题目标签 (如 "10(a)", "Question 21")
        paper_file_id: Paper file ID
        solution_file_id: Solution file ID
        exam_type: 试卷类型 ("type1" or "type2")
    
    Returns:
        QuestionOutput: 处理后的题目数据
    
    Raises:
        Exception: 如果处理失败
    """
    logger.info(f"⚙️  Processing question {question_index}: {question_label}")
    
    # Reset safety controller
    safety_controller.reset()
    
    # 创建FileSearchTool（同时搜索两个文件）
    file_search = FileSearchTool(
        file_ids=[paper_file_id, solution_file_id]
    )
    
    # 创建Agent
    processor_agent = Agent(
        name=f"Question Processor - {question_label}",
        instructions=get_file_based_processor_prompt(exam_type, question_label),
        tools=[file_search, compile_latex],
        output_type=QuestionOutput,
        model=settings.openai_model
    )
    
    # 执行
    try:
        result = await Runner.run(
            processor_agent,
            input=f"Process question {question_label} from the PDFs",
            max_turns=settings.max_turns_per_question
        )
        
        question_data = result.final_output
        
        # 设置question_index
        question_data.question_index = question_index
        
        # 验证question_number匹配
        if question_data.question_number != question_label:
            logger.warning(
                f"⚠️  Question label mismatch: expected '{question_label}', "
                f"got '{question_data.question_number}'"
            )
            # 强制修正
            question_data.question_number = question_label
        
        logger.info(f"✓ Completed question {question_index}: {question_label}")
        logger.info(f"   Question LaTeX: {len(question_data.question_latex)} chars")
        logger.info(f"   Answer LaTeX: {len(question_data.answer_latex)} chars")
        logger.info(f"   Images: {len(question_data.question_images)} (Q) + {len(question_data.answer_images)} (A)")
        
        return question_data
        
    except Exception as e:
        logger.error(f"❌ Failed to process question {question_label}: {e}")
        logger.exception(e)
        raise


async def process_all_questions_from_files(
    question_list: QuestionList,
    paper_file_id: str,
    solution_file_id: str,
    exam_type: str,
    continue_on_error: bool = True
) -> List[QuestionOutput]:
    """
    基于题目清单处理所有题目
    
    Args:
        question_list: Question Lister生成的题目清单
        paper_file_id: Paper file ID
        solution_file_id: Solution file ID
        exam_type: 试卷类型
        continue_on_error: 遇到错误是否继续处理后续题目
    
    Returns:
        处理成功的所有题目列表
    """
    questions = []
    failed_questions = []
    
    total = question_list.total_questions
    logger.info(f"🚀 Starting to process {total} questions...")
    
    for idx, question_item in enumerate(question_list.questions, 1):
        logger.info(f"\n{'='*60}")
        logger.info(f"Progress: {idx}/{total}")
        logger.info(f"{'='*60}")
        
        try:
            question_output = await process_question_from_files(
                question_index=question_item.question_index,
                question_label=question_item.question_label,
                paper_file_id=paper_file_id,
                solution_file_id=solution_file_id,
                exam_type=exam_type
            )
            questions.append(question_output)
            
        except Exception as e:
            logger.error(f"❌ Question {question_item.question_label} failed: {e}")
            failed_questions.append(question_item.question_label)
            
            if not continue_on_error:
                logger.error("Stopping due to error (continue_on_error=False)")
                raise
            
            logger.info("Continuing to next question...")
    
    # 总结
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing Summary")
    logger.info(f"{'='*60}")
    logger.info(f"✓ Successful: {len(questions)}/{total}")
    if failed_questions:
        logger.warning(f"❌ Failed: {len(failed_questions)}/{total}")
        logger.warning(f"   Failed questions: {', '.join(failed_questions)}")
    
    return questions
```

---

### 8. 工作流逻辑 (`workflow.py`) 🆕

```python
"""Complete workflow logic for V3 File-Based processing"""

import time
from pathlib import Path
from typing import Optional
from loguru import logger

from .config.settings import settings
from .models.schemas import ProcessedExam
from .preprocessing.pdf_renderer import preprocess_for_classification
from .services.file_uploader import (
    upload_pdfs_get_file_ids,
    cleanup_files,
    FileUploadResult
)
from .agents.classifier_agent import classify_exam_type
from .agents.question_lister_agent import list_all_questions
from .agents.file_based_question_processor import process_all_questions_from_files


async def run_file_based_workflow(
    paper_pdf_path: str,
    solution_pdf_path: str,
    exam_id: Optional[str] = None,
    output_dir: Optional[str] = None
) -> ProcessedExam:
    """
    执行完整的V3 File-Based Workflow
    
    Args:
        paper_pdf_path: Paper PDF路径
        solution_pdf_path: Solution PDF路径
        exam_id: 试卷ID（可选，默认使用时间戳）
        output_dir: 输出目录（可选）
    
    Returns:
        ProcessedExam: 处理结果
    
    Workflow Steps:
        1. 轻量级预处理（仅前3页用于分类）
        2. 分类器判断试卷类型
        3. 上传PDF获取file_id
        4. Question Lister列出所有题目
        5. Question Processor逐题处理
        6. 后处理和保存结果
        7. （可选）清理上传的文件
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
    logger.info(f"🚀 V3 File-Based Workflow - Starting")
    logger.info("="*80)
    logger.info(f"Exam ID: {exam_id}")
    logger.info(f"Paper: {paper_pdf_path}")
    logger.info(f"Solution: {solution_pdf_path}")
    logger.info(f"Output: {output_dir}")
    logger.info("="*80)
    
    file_upload_result: Optional[FileUploadResult] = None
    
    try:
        # === Step 1: 轻量级预处理 ===
        logger.info("\n" + "="*80)
        logger.info("Step 1: Lightweight Preprocessing (Classification Only)")
        logger.info("="*80)
        
        classification_data = await preprocess_for_classification(paper_pdf_path)
        logger.info(f"✓ Step 1 complete - Rendered {len(classification_data['selected_pages'])} pages")
        
        # === Step 2: 分类器 ===
        logger.info("\n" + "="*80)
        logger.info("Step 2: Exam Type Classification")
        logger.info("="*80)
        
        exam_type = await classify_exam_type(classification_data)
        logger.info(f"✓ Step 2 complete - Exam type: {exam_type}")
        
        # === Step 3: 上传PDF获取file_id ===
        logger.info("\n" + "="*80)
        logger.info("Step 3: Uploading PDFs to OpenAI")
        logger.info("="*80)
        
        file_upload_result = await upload_pdfs_get_file_ids(
            paper_pdf_path,
            solution_pdf_path
        )
        logger.info(f"✓ Step 3 complete")
        logger.info(f"   Paper file ID: {file_upload_result.paper_file_id}")
        logger.info(f"   Solution file ID: {file_upload_result.solution_file_id}")
        
        # === Step 4: Question Lister ===
        logger.info("\n" + "="*80)
        logger.info("Step 4: Listing All Questions")
        logger.info("="*80)
        
        question_list = await list_all_questions(
            exam_type=exam_type,
            paper_file_id=file_upload_result.paper_file_id
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
        
        # === Step 5: Question Processor ===
        logger.info("\n" + "="*80)
        logger.info("Step 5: Processing All Questions")
        logger.info("="*80)
        
        questions = await process_all_questions_from_files(
            question_list=question_list,
            paper_file_id=file_upload_result.paper_file_id,
            solution_file_id=file_upload_result.solution_file_id,
            exam_type=exam_type,
            continue_on_error=True  # 继续处理后续题目
        )
        logger.info(f"✓ Step 5 complete - Processed {len(questions)} questions")
        
        # === Step 6: 构建结果 ===
        processing_time = time.time() - start_time
        
        result = ProcessedExam(
            exam_id=exam_id,
            exam_type=exam_type,
            total_questions=len(questions),
            questions=questions,
            paper_pdf_path=paper_pdf_path,
            solution_pdf_path=solution_pdf_path,
            paper_file_id=file_upload_result.paper_file_id,
            solution_file_id=file_upload_result.solution_file_id,
            processing_time_seconds=processing_time,
            workflow_version="v3_file_based"
        )
        
        # 保存结果
        result_file = output_dir / f"{exam_id}_processed.json"
        result_file.write_text(
            result.model_dump_json(indent=2),
            encoding='utf-8'
        )
        logger.info(f"   Saved result to: {result_file}")
        
        # === 最终总结 ===
        logger.info("\n" + "="*80)
        logger.info("✅ Processing Complete!")
        logger.info("="*80)
        logger.info(f"Exam ID: {exam_id}")
        logger.info(f"Exam Type: {exam_type}")
        logger.info(f"Total Questions: {len(questions)}")
        logger.info(f"Processing Time: {processing_time:.1f}s")
        logger.info(f"Output Directory: {output_dir}")
        logger.info("="*80)
        
        return result
        
    finally:
        # === Step 7: 清理文件（可选） ===
        if settings.auto_cleanup_files and file_upload_result:
            logger.info("\n" + "="*80)
            logger.info("Step 7: Cleaning Up Files")
            logger.info("="*80)
            
            await cleanup_files([
                file_upload_result.paper_file_id,
                file_upload_result.solution_file_id
            ])
            logger.info("✓ Step 7 complete - Files cleaned up")
```

---

### 9. 主入口 (`main.py`)

```python
"""Main entry point for import_v4 - delegates to workflow"""

from typing import Optional
from .models.schemas import ProcessedExam
from .workflow import run_file_based_workflow


async def process_exam_file_based(
    paper_pdf_path: str,
    solution_pdf_path: str,
    exam_id: Optional[str] = None,
    output_dir: Optional[str] = None
) -> ProcessedExam:
    """
    V3 File-Based Workflow 主入口
    
    Args:
        paper_pdf_path: Paper PDF路径
        solution_pdf_path: Solution PDF路径
        exam_id: 试卷ID（可选，默认使用时间戳）
        output_dir: 输出目录（可选）
    
    Returns:
        ProcessedExam: 处理结果
    """
    return await run_file_based_workflow(
        paper_pdf_path=paper_pdf_path,
        solution_pdf_path=solution_pdf_path,
        exam_id=exam_id,
        output_dir=output_dir
    )


async def process_exam(
    paper_pdf_path: str,
    solution_pdf_path: str,
    exam_id: Optional[str] = None,
    output_dir: Optional[str] = None
) -> ProcessedExam:
    """
    向后兼容的主入口函数
    
    Args:
        paper_pdf_path: Paper PDF路径
        solution_pdf_path: Solution PDF路径
        exam_id: 试卷ID（可选）
        output_dir: 输出目录（可选）
    
    Returns:
        ProcessedExam: 处理结果
    """
    return await process_exam_file_based(
        paper_pdf_path, solution_pdf_path, exam_id, output_dir
    )
```

---

### 10. 测试脚本示例

创建 `test_file_based.py`:

```python
"""Test script for V3 File-Based Workflow"""

import asyncio
from pathlib import Path
from loguru import logger

from import_v4.main import process_exam_file_based
from import_v4.config.settings import settings
from import_v4.utils.logger import setup_logger


async def main():
    """测试主函数"""
    
    # 设置日志
    setup_logger()
    
    # 测试文件路径
    test_dir = Path(__file__).parent.parent / "test" / "test_input"
    paper_pdf = test_dir / "paper.pdf"
    solution_pdf = test_dir / "solution.pdf"
    
    if not paper_pdf.exists():
        logger.error(f"Paper PDF not found: {paper_pdf}")
        return
    
    if not solution_pdf.exists():
        logger.error(f"Solution PDF not found: {solution_pdf}")
        return
    
    # 运行处理
    try:
        result = await process_exam_file_based(
            paper_pdf_path=str(paper_pdf),
            solution_pdf_path=str(solution_pdf),
            exam_id="test_file_based_001",
            output_dir="test_output/test_file_based_001"
        )
        
        logger.info("\n" + "="*80)
        logger.info("Test Results:")
        logger.info("="*80)
        logger.info(f"Exam Type: {result.exam_type}")
        logger.info(f"Total Questions: {result.total_questions}")
        logger.info(f"Processing Time: {result.processing_time_seconds:.1f}s")
        logger.info(f"Paper File ID: {result.paper_file_id}")
        logger.info(f"Solution File ID: {result.solution_file_id}")
        
        # 显示前几道题
        for i, q in enumerate(result.questions[:3], 1):
            logger.info(f"\nQuestion {i}: {q.question_number}")
            logger.info(f"  Marks: {q.marks}")
            logger.info(f"  Question LaTeX length: {len(q.question_latex)}")
            logger.info(f"  Answer LaTeX length: {len(q.answer_latex)}")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        logger.exception(e)


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 关键接口和数据流

### 架构层次

```
main.py (入口层)
    ↓ 调用
workflow.py (工作流层)
    ↓ 编排
各个模块 (执行层)
```

### 数据流图

```
Input PDFs
    ↓
main.py: process_exam_file_based()
    ↓
workflow.py: run_file_based_workflow()
    ↓
[preprocess_for_classification]
    ↓
selected_pages (倒数第2、4、6页，或最后N页)
    ↓
[classify_exam_type]
    ↓
exam_type
    ↓
[upload_pdfs_get_file_ids]
    ↓
FileUploadResult {paper_file_id, solution_file_id}
    ↓
[list_all_questions]
    ↓
QuestionList {exam_type, total_questions, questions[]}
    ↓
[process_all_questions_from_files] ← 循环
    ↓
List[QuestionOutput]
    ↓
ProcessedExam
    ↓ 返回
main.py
```

### 关键接口总结

| 模块 | 输入 | 输出 |
|------|------|------|
| `main.py::process_exam_file_based` | paper_pdf, solution_pdf, exam_id, output_dir | ProcessedExam |
| `workflow.py::run_file_based_workflow` | paper_pdf, solution_pdf, exam_id, output_dir | ProcessedExam |
| `preprocess_for_classification` | paper_pdf_path | {selected_pages, total_pages} |
| `classify_exam_type` | classification_data | exam_type |
| `upload_pdfs_get_file_ids` | paper_pdf, solution_pdf | FileUploadResult |
| `list_all_questions` | exam_type, paper_file_id | QuestionList |
| `process_question_from_files` | question_item, file_ids, exam_type | QuestionOutput |
| `process_all_questions_from_files` | question_list, file_ids | List[QuestionOutput] |

### 架构设计优势

**关注点分离**：
- `main.py` - 纯粹的入口点，提供简洁的API接口
- `workflow.py` - 专注于工作流编排和步骤协调
- 各模块 - 专注于具体功能实现

**可维护性**：
- 工作流逻辑集中在 `workflow.py`，便于理解和修改
- 新增工作流步骤只需修改 `workflow.py`
- 入口接口保持稳定，不受工作流变化影响

**可测试性**：
- 可以直接测试 `workflow.py` 的工作流逻辑
- 可以单独测试 `main.py` 的接口层
- 各个模块可以独立单元测试

**可扩展性**：
- 未来可以在 `workflow.py` 中添加多种工作流（如 v4, v5）
- `main.py` 可以根据参数选择不同的工作流
- 保持向后兼容性

### 页面选择策略说明

**为什么使用倒数第 2、4、6 页进行分类？**

1. **答题区域判断更准确**
   - 试卷前面通常是题目说明和开始部分
   - 试卷后面更可能包含答题区域
   - Type1 后面继续密集题目，Type2 后面有明显空白

2. **避免封面干扰**
   - 第一页通常是封面、说明
   - 可能不包含实际题目内容
   - 对分类帮助不大

3. **采样均匀**
   - 倒数第 2、4、6 页分布较均匀
   - 可以覆盖试卷中后部分的不同区域
   - 提高分类准确性

4. **与 import_v3 保持一致**
   - 已经过实际验证的策略
   - 分类准确率较高
   - 保持系统一致性

---

## 配置示例

创建 `.env` 文件:

```bash
# OpenAI配置
EXAM_PROCESSOR_OPENAI_API_KEY=sk-your-api-key-here
EXAM_PROCESSOR_OPENAI_MODEL=gpt-4o

# Agent配置
EXAM_PROCESSOR_MAX_TURNS_PER_QUESTION=15
EXAM_PROCESSOR_MAX_LATEX_FIX_ATTEMPTS=2
EXAM_PROCESSOR_LISTER_MAX_TURNS=10
EXAM_PROCESSOR_CLASSIFIER_MAX_TURNS=5

# 文件配置
EXAM_PROCESSOR_AUTO_CLEANUP_FILES=false
EXAM_PROCESSOR_SAVE_QUESTION_LIST=true

# 输出配置
EXAM_PROCESSOR_OUTPUT_DIR=output
```

---

## 测试策略

### 单元测试

```python
# tests/test_file_uploader.py
import pytest
from import_v4.services.file_uploader import upload_pdfs_get_file_ids

@pytest.mark.asyncio
async def test_upload_pdfs():
    result = await upload_pdfs_get_file_ids("paper.pdf", "solution.pdf")
    assert result.paper_file_id is not None
    assert result.solution_file_id is not None
```

### 集成测试

```python
# tests/test_integration.py
import pytest
from import_v4.main import process_exam_file_based

@pytest.mark.asyncio
async def test_full_workflow():
    result = await process_exam_file_based(
        "test_paper.pdf",
        "test_solution.pdf",
        exam_id="test_001"
    )
    assert result.total_questions > 0
    assert result.exam_type in ["type1", "type2"]
```

---

## 性能监控

在代码中添加性能日志:

```python
import time

def log_performance(step_name: str):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start = time.time()
            result = await func(*args, **kwargs)
            duration = time.time() - start
            logger.info(f"⏱️  {step_name}: {duration:.2f}s")
            return result
        return wrapper
    return decorator

# 使用
@log_performance("Question Lister")
async def list_all_questions(...):
    ...
```

---

## 下一步

1. ✅ 完成基础架构代码
2. ✅ 实现Question Lister Agent
3. ✅ 实现File-Based Question Processor
4. ⏳ 单元测试
5. ⏳ 集成测试
6. ⏳ 性能优化
7. ⏳ 文档完善

---

**文档版本**: V1.0  
**创建日期**: 2024年10月  
**状态**: 实现指南

