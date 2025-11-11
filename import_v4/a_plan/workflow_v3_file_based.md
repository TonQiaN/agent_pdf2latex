# 试卷处理系统 - V3 File-Based Workflow

## 概述

V3是对现有Scanner模式的重大升级，采用**File ID复用**策略，通过**两阶段处理**（Question Lister + Question Processor）实现更高效、更经济的试卷处理流程。

### 核心改进

| 改进点 | 说明 | 优势 |
|--------|------|------|
| 💰 **File ID复用** | PDF只上传一次，获取持久化file_id | 成本降低，无需重复上传 |
| 🎯 **两阶段处理** | 先列题目清单，再逐题处理 | 职责清晰，易于测试 |
| ⚡ **按需渲染** | 只在分类时渲染图片，处理时用原PDF | 速度提升，减少预处理 |
| 🔄 **支持重试** | file_id持久化，可断点续传 | 可靠性提升 |
| 📊 **智能搜索** | FileSearchTool语义搜索 | 适应各种布局 |

---

## 完整流程图

```
┌──────────────────────────────────────────────────────────────┐
│                    输入: Paper PDF + Solution PDF             │
└─────────────────────┬────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────────────────┐
│  Step 1: 轻量级预处理 (仅用于分类)                             │
│  preprocessing/pdf_renderer.py                                │
│  - 渲染前3页为图片 (用于分类器)                                │
│  - 不渲染全部页面                                              │
└─────────────────────┬────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────────────────┐
│  Step 2: 试卷类型分类器                                        │
│  agents/classifier_agent.py                                   │
│  - 分析前3页图片                                               │
│  - 输出: exam_type ("type1" or "type2")                      │
└─────────────────────┬────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────────────────┐
│  Step 3: 上传PDF获取File ID 🆕                                │
│  services/file_uploader.py                                    │
│                                                               │
│  client = AsyncOpenAI()                                       │
│                                                               │
│  paper_file = await client.files.create(                     │
│      file=open(paper_pdf_path, "rb"),                        │
│      purpose="assistants"                                    │
│  )                                                            │
│  paper_file_id = paper_file.id                               │
│                                                               │
│  solution_file = await client.files.create(                  │
│      file=open(solution_pdf_path, "rb"),                     │
│      purpose="assistants"                                    │
│  )                                                            │
│  solution_file_id = solution_file.id                         │
│                                                               │
│  💡 关键优势: file_id可复用，后续所有操作共享                  │
└─────────────────────┬────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────────────────┐
│  Step 4: Question Lister Agent 🆕                             │
│  agents/question_lister_agent.py                              │
│                                                               │
│  职责: 快速扫描paper，列出所有题目清单                         │
│                                                               │
│  输入:                                                         │
│    - exam_type: "type1" or "type2"                           │
│    - paper_file_id: 已上传的paper文件ID                       │
│                                                               │
│  使用工具:                                                     │
│    - FileSearchTool(file_ids=[paper_file_id])               │
│                                                               │
│  输出: QuestionList                                           │
│    {                                                          │
│      "exam_type": "type1",                                   │
│      "total_questions": 15,                                  │
│      "questions": [                                          │
│        {"question_index": 1, "question_label": "10(a)"},    │
│        {"question_index": 2, "question_label": "10(b)"},    │
│        {"question_index": 3, "question_label": "11(a)"},    │
│        ...                                                   │
│      ]                                                       │
│    }                                                         │
└─────────────────────┬────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────────────────┐
│  Step 5: 逐题处理循环                                          │
│                                                               │
│  for each question in QuestionList.questions:                │
│      ↓                                                        │
│   ┌──────────────────────────────────────────────┐          │
│   │  File-Based Question Processor Agent 🆕       │          │
│   │  agents/file_based_question_processor.py     │          │
│   ├──────────────────────────────────────────────┤          │
│   │  输入:                                        │          │
│   │    - question_index: int                     │          │
│   │    - question_label: str (如 "10(a)")        │          │
│   │    - paper_file_id: str                      │          │
│   │    - solution_file_id: str                   │          │
│   │    - exam_type: str                          │          │
│   │                                              │          │
│   │  使用工具:                                    │          │
│   │    - FileSearchTool(file_ids=[               │          │
│   │        paper_file_id,                        │          │
│   │        solution_file_id                      │          │
│   │      ])                                      │          │
│   │    - compile_latex()                         │          │
│   │                                              │          │
│   │  工作流程:                                    │          │
│   │  1. FileSearchTool搜索question_label在paper  │          │
│   │  2. 提取题目完整文本                          │          │
│   │  3. FileSearchTool搜索答案在solution         │          │
│   │  4. 提取答案完整文本                          │          │
│   │  5. 生成question_latex                       │          │
│   │  6. 生成answer_latex                         │          │
│   │  7. 标注图片位置(bbox估计)                   │          │
│   │  8. compile_latex验证                        │          │
│   │  9. 失败则修复(最多2次)                      │          │
│   │  10. 返回QuestionOutput                      │          │
│   └──────────────────────────────────────────────┘          │
│                                                               │
└─────────────────────┬────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────────────────┐
│  Step 6: 后处理                                               │
│  postprocessing/                                              │
│  - image_extractor.py: 根据bbox从原PDF裁剪图片                │
│  - metadata_extractor.py: 提取元数据                          │
└─────────────────────┬────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────────────────┐
│  输出                                                         │
│  - {exam_id}_processed.json                                  │
│  - {exam_id}_images/                                         │
│  - question_list.json (题目清单)                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 详细步骤说明

### Step 1: 轻量级预处理

**文件**: `preprocessing/pdf_renderer.py`

**改进**: 只渲染前3页用于分类，不再预处理所有页面

```python
async def preprocess_for_classification(paper_pdf_path: str) -> dict:
    """
    轻量级预处理：只渲染前3页用于分类
    
    Returns:
        {
            "first_pages": [page1_data, page2_data, page3_data],
            "paper_pdf_path": str
        }
    """
    renderer = PDFRenderer()
    doc = fitz.open(paper_pdf_path)
    total_pages = len(doc)
    
    # 只渲染前3页
    first_pages = []
    for page_num in range(1, min(4, total_pages + 1)):
        page_data = renderer.render_page(paper_pdf_path, page_num)
        first_pages.append(page_data)
    
    return {
        "first_pages": first_pages,
        "paper_pdf_path": paper_pdf_path,
        "total_pages": total_pages
    }
```

---

### Step 2: 分类器

**文件**: `agents/classifier_agent.py`

**保持不变**，输入改为只使用前3页图片。

---

### Step 3: 上传PDF获取File ID 🆕

**新建文件**: `services/file_uploader.py`

```python
"""File uploader service for OpenAI"""

from openai import AsyncOpenAI
from loguru import logger
from ..config.settings import settings


async def upload_pdfs_get_file_ids(
    paper_pdf_path: str,
    solution_pdf_path: str
) -> dict:
    """
    上传PDF到OpenAI，获取file_id
    
    Args:
        paper_pdf_path: Paper PDF路径
        solution_pdf_path: Solution PDF路径
    
    Returns:
        {
            "paper_file_id": str,
            "solution_file_id": str,
            "paper_file": File object,
            "solution_file": File object
        }
    """
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    logger.info("Uploading paper PDF to OpenAI...")
    with open(paper_pdf_path, 'rb') as f:
        paper_file = await client.files.create(
            file=f,
            purpose="assistants"
        )
    logger.info(f"✓ Paper uploaded: {paper_file.id}")
    
    logger.info("Uploading solution PDF to OpenAI...")
    with open(solution_pdf_path, 'rb') as f:
        solution_file = await client.files.create(
            file=f,
            purpose="assistants"
        )
    logger.info(f"✓ Solution uploaded: {solution_file.id}")
    
    return {
        "paper_file_id": paper_file.id,
        "solution_file_id": solution_file.id,
        "paper_file": paper_file,
        "solution_file": solution_file
    }


async def cleanup_files(client: AsyncOpenAI, file_ids: list):
    """
    清理上传的文件（可选）
    
    Args:
        client: OpenAI client
        file_ids: 文件ID列表
    """
    for file_id in file_ids:
        try:
            await client.files.delete(file_id)
            logger.info(f"✓ File deleted: {file_id}")
        except Exception as e:
            logger.warning(f"Failed to delete file {file_id}: {e}")
```

---

### Step 4: Question Lister Agent 🆕

**新建文件**: `agents/question_lister_agent.py`

```python
"""Question Lister Agent - List all questions from paper PDF"""

from typing import List
from loguru import logger
from agents import Agent, Runner, FileSearchTool
from pydantic import BaseModel

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
- Question 10 is a section title, not an independent question
- 10(a), 10(b), 10(c) are **independent questions** (minimum splitting unit)
- 10(c)(i), 10(c)(ii) are **sub-parts** of 10(c), NOT separate questions
- Recognition pattern: ^\\d+\\([a-z]\\) indicates start of independent question
"""
    else:
        cutting_rule = """
【Type2 Rules】(Answer on Paper):
- Question 21 is **one complete question** (minimum splitting unit)
- 21(a), 21(b), 21(c) are **sub-parts**, NOT separate questions
- Recognition pattern: ^Question \\d+ indicates start of question
"""
    
    return f"""You are a Question Lister Agent. Your task is to scan the entire paper PDF and create a complete list of all questions.

=== Exam Type ===
{exam_type}

=== Question Splitting Rules ===
{cutting_rule}

=== Your Task ===
1. Use the FileSearchTool to analyze the entire paper PDF
2. Identify ALL questions in the document
3. For each question, record:
   - question_index: Sequential number (1, 2, 3, ...)
   - question_label: Exact label from paper (e.g., "10(a)", "10(b)", "11(a)")

=== Important Notes ===
- Be thorough: scan the ENTIRE document
- Follow the splitting rules strictly
- Preserve exact question labels as they appear in the paper
- Number questions sequentially starting from 1
- Do NOT include sub-parts as separate questions

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

Begin scanning now using the FileSearchTool.
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
    """
    logger.info(f"Listing all questions from paper (file_id: {paper_file_id})...")
    
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
    result = await Runner.run(
        lister_agent,
        input="List all questions from the paper PDF",
        max_turns=10
    )
    
    question_list = result.final_output
    
    logger.info(f"✓ Found {question_list.total_questions} questions")
    for q in question_list.questions[:5]:
        logger.info(f"  [{q.question_index}] {q.question_label}")
    if question_list.total_questions > 5:
        logger.info(f"  ... and {question_list.total_questions - 5} more")
    
    return question_list
```

---

### Step 5: File-Based Question Processor Agent 🆕

**新建文件**: `agents/file_based_question_processor.py`

```python
"""File-Based Question Processor - Process questions using file IDs"""

from loguru import logger
from agents import Agent, Runner, FileSearchTool

from ..config.settings import settings
from ..models.schemas import QuestionOutput
from ..tools.latex_compiler import compile_latex
from .safety_controller import safety_controller


def get_file_based_processor_prompt(
    exam_type: str,
    question_label: str
) -> str:
    """
    生成基于file_id的Question Processor prompt
    """
    if exam_type == "type1":
        cutting_rule = "Keep sub-parts (i)(ii)(iii) in question content"
    else:
        cutting_rule = "Keep sub-parts (a)(b)(c) in question content"
    
    return f"""You are a Question Processor Agent. Process question {question_label} from the PDFs.

=== Your Task ===
Process question: {question_label}

=== Available Files ===
You have access to:
- Paper PDF (contains the question)
- Solution PDF (contains the answer)

Use FileSearchTool to search and extract content from both files.

=== Workflow ===

1️⃣ **Find the question in paper**
   - Use FileSearchTool to search for "{question_label}"
   - Read the complete question text
   - Note: question may span multiple pages

2️⃣ **Find the answer in solution**
   - Use FileSearchTool to search for answer to "{question_label}"
   - Read the complete answer text
   - Note: answer may span multiple pages

3️⃣ **Generate LaTeX**
   - Convert question text to question_latex
   - Convert answer text to answer_latex
   - {cutting_rule}

4️⃣ **Identify images**
   - Mark approximate locations of images
   - Provide bbox estimates: [x1, y1, x2, y2]
   - Note which page each image appears on

5️⃣ **Verify LaTeX**
   - Call compile_latex(question_latex, "question")
   - Call compile_latex(answer_latex, "answer")
   - Fix errors if compilation fails (max 2 attempts)

6️⃣ **Return output**
   - question_number: "{question_label}"
   - question_latex: generated LaTeX
   - answer_latex: generated LaTeX
   - question_images: list of image info
   - answer_images: list of image info
   - marks: extract from question
   - reasoning: your thought process

=== Important Notes ===
- Use FileSearchTool to search, don't guess page numbers
- Extract complete content even if it spans pages
- Keep sub-parts in LaTeX content
- Image bbox format: [x1, y1, x2, y2], origin at top-left

Begin processing now.
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
        question_index: 题目序号
        question_label: 题目标签 (如 "10(a)")
        paper_file_id: Paper file ID
        solution_file_id: Solution file ID
        exam_type: 试卷类型
    
    Returns:
        QuestionOutput: 处理后的题目数据
    """
    logger.info(f"Processing question {question_index}: {question_label}")
    
    # Reset safety controller
    safety_controller.reset()
    
    # 创建FileSearchTool（同时搜索两个文件）
    file_search = FileSearchTool(
        file_ids=[paper_file_id, solution_file_id]
    )
    
    # 创建Agent
    processor_agent = Agent(
        name="Question Processor",
        instructions=get_file_based_processor_prompt(exam_type, question_label),
        tools=[file_search, compile_latex],
        output_type=QuestionOutput,
        model=settings.openai_model
    )
    
    # 执行
    try:
        result = await Runner.run(
            processor_agent,
            input=f"Process question {question_label}",
            max_turns=settings.max_turns_per_question
        )
        
        question_data = result.final_output
        
        # 设置question_index
        question_data.question_index = question_index
        
        # 验证question_number
        if question_data.question_number != question_label:
            logger.warning(
                f"Question label mismatch: expected {question_label}, "
                f"got {question_data.question_number}"
            )
        
        logger.info(f"✓ Completed question {question_index}: {question_label}")
        
        return question_data
        
    except Exception as e:
        logger.error(f"Failed to process question {question_label}: {e}")
        logger.exception(e)
        raise


async def process_all_questions_from_files(
    question_list: "QuestionList",
    paper_file_id: str,
    solution_file_id: str,
    exam_type: str
) -> list[QuestionOutput]:
    """
    基于题目清单处理所有题目
    
    Args:
        question_list: Question Lister生成的题目清单
        paper_file_id: Paper file ID
        solution_file_id: Solution file ID
        exam_type: 试卷类型
    
    Returns:
        处理后的所有题目
    """
    questions = []
    
    logger.info(f"Processing {question_list.total_questions} questions...")
    
    for question_item in question_list.questions:
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
            logger.error(f"Skipping question {question_item.question_label} due to error")
            # 可以选择继续或停止
            continue
    
    return questions
```

---

### Step 6: 后处理

**保持不变**，继续使用现有的后处理模块。

---

## 新增数据模型

**文件**: `models/schemas.py` 添加

```python
class QuestionItem(BaseModel):
    """单个题目信息（来自Lister）"""
    model_config = ConfigDict(extra="forbid")
    
    question_index: int = Field(..., description="Sequential index (1-based)")
    question_label: str = Field(..., description="Question label like '10(a)'")


class QuestionList(BaseModel):
    """题目清单（Lister的输出）"""
    model_config = ConfigDict(extra="forbid")
    
    exam_type: str = Field(..., description="type1 or type2")
    total_questions: int = Field(..., description="Total number of questions")
    questions: List[QuestionItem] = Field(..., description="List of all questions")
```

---

## 主流程编排

**文件**: `main.py` 新增模式

```python
async def process_exam(
    paper_pdf_path: str,
    solution_pdf_path: str,
    exam_id: str = None,
    use_file_based: bool = False  # 🆕 新模式
) -> ProcessedExam:
    """
    主入口
    
    Args:
        use_file_based: If True, use file-based V3 workflow
    """
    # ... setup ...
    
    if use_file_based:
        # === V3: File-Based Workflow ===
        
        # Step 1: 轻量级预处理（只渲染前3页）
        logger.info("Step 1: Lightweight preprocessing...")
        first_pages_data = await preprocess_for_classification(paper_pdf_path)
        
        # Step 2: 分类
        logger.info("Step 2: Classifying exam type...")
        exam_type = await classify_exam_type(first_pages_data)
        
        # Step 3: 上传PDF获取file_id
        logger.info("Step 3: Uploading PDFs to get file IDs...")
        from .services.file_uploader import upload_pdfs_get_file_ids
        file_ids = await upload_pdfs_get_file_ids(
            paper_pdf_path, solution_pdf_path
        )
        
        # Step 4: 列出所有题目
        logger.info("Step 4: Listing all questions...")
        from .agents.question_lister_agent import list_all_questions
        question_list = await list_all_questions(
            exam_type, file_ids["paper_file_id"]
        )
        
        # 保存题目清单
        question_list_file = output_dir / "question_list.json"
        question_list_file.write_text(question_list.model_dump_json(indent=2))
        
        # Step 5: 处理所有题目
        logger.info("Step 5: Processing all questions...")
        from .agents.file_based_question_processor import process_all_questions_from_files
        questions = await process_all_questions_from_files(
            question_list=question_list,
            paper_file_id=file_ids["paper_file_id"],
            solution_file_id=file_ids["solution_file_id"],
            exam_type=exam_type
        )
        
        # Optional: 清理文件
        # await cleanup_files(client, [file_ids["paper_file_id"], file_ids["solution_file_id"]])
    
    else:
        # 现有流程...
        pass
    
    # Step 6: 后处理...
    # 返回结果...
```

---

## 与现有流程对比

### Scanner V2 模式
```
1. 预处理 → 渲染所有页面为base64图片
2. 分类
3. 上传PDF到Vector Store
4. Scanner Agent扫描 → 生成ScanResult索引
5. 删除Vector Store
6. Question Processor用base64图片处理每道题
7. 后处理
```

### File-Based V3 模式 🆕
```
1. 预处理 → 只渲染前3页（用于分类）
2. 分类
3. 上传PDF → 获取持久化file_id
4. Question Lister Agent → 生成QuestionList
5. Question Processor用file_id处理每道题
6. 后处理
7. (可选) 清理file_id
```

### 优势对比

| 方面 | Scanner V2 | File-Based V3 | 改进 |
|------|-----------|---------------|------|
| **预处理时间** | 全部页面 | 只前3页 | ⚡ 快5-10倍 |
| **上传成本** | Vector Store创建+删除 | File上传一次 | 💰 更便宜 |
| **file复用** | 不可复用 | 可复用 | ✅ 支持重试 |
| **处理方式** | base64图片 | FileSearchTool | 📊 更灵活 |
| **两阶段** | 无 | Lister + Processor | 🎯 更清晰 |

---

## 实现计划

### Phase 1: 基础架构（1-2天）

- [ ] 创建 `services/file_uploader.py`
  - upload_pdfs_get_file_ids()
  - cleanup_files()

- [ ] 创建 `models/schemas.py` 新模型
  - QuestionItem
  - QuestionList

- [ ] 修改 `preprocessing/pdf_renderer.py`
  - 添加 preprocess_for_classification() 函数

### Phase 2: Question Lister Agent（2-3天）

- [ ] 创建 `agents/question_lister_agent.py`
  - get_question_lister_prompt()
  - list_all_questions()

- [ ] 测试Question Lister
  - 测试type1试卷
  - 测试type2试卷
  - 验证题目清单准确性

### Phase 3: File-Based Processor Agent（3-4天）

- [ ] 创建 `agents/file_based_question_processor.py`
  - get_file_based_processor_prompt()
  - process_question_from_files()
  - process_all_questions_from_files()

- [ ] 测试Question Processor
  - 测试单题处理
  - 测试LaTeX生成
  - 测试图片标注

### Phase 4: 主流程集成（2-3天）

- [ ] 修改 `main.py`
  - 添加 use_file_based 参数
  - 实现V3流程分支
  - 集成所有步骤

- [ ] 更新 `agents/__init__.py`
  - 导出新的Agent函数

### Phase 5: 端到端测试（2-3天）

- [ ] 测试完整流程
  - 多份试卷测试
  - 对比V2和V3结果
  - 性能对比

- [ ] 优化和bug修复

### Phase 6: 文档和部署（1-2天）

- [ ] 更新文档
- [ ] 添加使用示例
- [ ] 部署到生产环境

---

## 使用示例

```python
from import_v3.main import process_exam

# V3 File-Based 模式
result = await process_exam(
    paper_pdf_path="paper.pdf",
    solution_pdf_path="solution.pdf",
    exam_id="exam_001",
    use_file_based=True  # 🆕 启用V3模式
)

print(f"✓ 处理完成：{result.total_questions}道题")
```

---

## 预期效果

### 性能提升

| 指标 | V2 Scanner | V3 File-Based | 提升 |
|------|------------|---------------|------|
| 预处理时间 | ~10s | ~2s | **80% ↓** |
| 上传成本 | Vector Store | File | **50% ↓** |
| 总时间 | ~120s | ~60s | **50% ↓** |
| 可重试 | ❌ | ✅ | ✅ |

### 代码质量

- ✅ 职责更清晰（Lister vs Processor）
- ✅ 易于测试（两个独立Agent）
- ✅ 易于调试（题目清单可视化）
- ✅ 易于扩展（基于file_id的其他应用）

---

## 总结

V3 File-Based Workflow是对现有系统的重大升级，通过：
1. **File ID复用** - 节约成本和时间
2. **两阶段处理** - 职责清晰，易于调试
3. **按需渲染** - 只在需要时渲染图片
4. **智能搜索** - FileSearchTool适应各种布局

实现了更高效、更经济、更可靠的试卷处理系统！🚀

---

**文档版本**: V3.0  
**创建日期**: 2024年10月  
**状态**: 待实现

