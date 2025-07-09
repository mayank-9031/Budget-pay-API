from pydantic import BaseModel


class ChatbotRequest(BaseModel):
    query: str


class ChatbotResponse(BaseModel):
    response: str 