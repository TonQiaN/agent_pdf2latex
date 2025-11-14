"""
JSON Schema Definitions
Defines the structure of JSON responses from agents
"""

from dataclasses import dataclass
from typing import List, Optional, Literal, Callable
from pydantic import BaseModel, Field
from langchain.agents.middleware import wrap_model_call, ModelRequest, ModelResponse

class ClassifyResponse(BaseModel):
    """
    Step 0: classify agent 的输出
    """
    exam_type: Literal["type1", "type2"]
    reasoning: str = Field(..., description="Reasoning for the classification decision")
    confidence: Optional[float] = Field(None, description="Confidence in the classification decision")

class QuestionItem(BaseModel):
    question_index: int = Field(..., description="Question index")
    question_label: str = Field(..., description="Question label")

class ListerResponse(BaseModel):
    """
    Step 1: lister agent 的输出
    """
    exam_type: Literal["type1", "type2"]
    total_questions: int = Field(..., description="Total number of questions")
    questions: List[QuestionItem] = Field(..., description="List of questions' information")

@wrap_model_call
def context_based_output(
    request: ModelRequest,
    handler: Callable[[ModelRequest], ModelResponse]
) -> ModelResponse:
    """
    Select output format based on Runtime Context.
    
    同步版本，支持 invoke()
    """
    step = request.runtime.context.step
    if step == "classify":
        print("context_based_output: classify")
        request = request.override(response_format=ClassifyResponse)
    elif step == "lister":
        print("context_based_output: lister")
        request = request.override(response_format=ListerResponse)
    else:
        raise ValueError(f"Unsupported step: {step}")

    return handler(request)