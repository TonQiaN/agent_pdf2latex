from typing import Callable, List, Optional, Literal
from pydantic import BaseModel, Field
from langchain.agents.middleware import wrap_model_call, ModelRequest, ModelResponse
from langchain.agents.structured_output import ProviderStrategy

class ClassifyResponse(BaseModel):
    exam_type: Literal["type1", "type2"]
    reasoning: str = Field(description="Reasoning for the classification decision")
    confidence: Optional[float] = Field(None, description="Confidence in the classification decision")

class QuestionItem(BaseModel):
    question_index: int = Field(description="Question index")
    question_label: str = Field(description="Question label")

class ListerResponse(BaseModel):
    exam_type: Literal["type1", "type2"]
    total_questions: int = Field(description="Total number of questions")
    questions: List[QuestionItem] = Field(description="List of questions' index and label")


@wrap_model_call
def context_based_output(
    request: ModelRequest,
    handler: Callable[[ModelRequest], ModelResponse]
) -> ModelResponse:
    """OpenAI-only：用 ProviderStrategy 选择结构化输出 Schema；不再改 kwargs。"""
    step = request.runtime.context.step
    if step == "classify":
        schema = ClassifyResponse
        print("context_based_output: classify")
    elif step == "lister":
        schema = ListerResponse
        print("context_based_output: lister")
    else:
        raise ValueError(f"Unsupported step: {step}")

    request = request.override(response_format=ProviderStrategy(schema))
    return handler(request)
