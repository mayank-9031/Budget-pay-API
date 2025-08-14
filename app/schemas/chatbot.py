from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Dict, Any


class ChatbotRequest(BaseModel):
    query: str


class ChatbotResponse(BaseModel):
    response: str 


class ChatCommandRequest(BaseModel):
    command: str = Field(..., description="Natural language command from the user")
    dry_run: bool = Field(False, description="If true, do not execute actions, only plan")


class ChatCommandAction(BaseModel):
    type: Literal[
        "create_transaction",
        "update_transaction",
        "delete_transaction",
        "create_category",
        "update_category",
        "delete_category",
    ]
    params: Dict[str, Any]


class ExecutedActionResult(BaseModel):
    type: str
    status: Literal["success", "error"]
    message: str
    data: Optional[Dict[str, Any]] = None


class ChatCommandPlan(BaseModel):
    actions: List[ChatCommandAction]


class ChatCommandResponse(BaseModel):
    plan: ChatCommandPlan
    executed: List[ExecutedActionResult]
    response: str