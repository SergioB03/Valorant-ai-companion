from fastapi import APIRouter
from pydantic import BaseModel
from app.services.claude_service import ask_claude

router = APIRouter(prefix="/claude", tags=["claude"])

class PromptRequest(BaseModel):
    prompt: str

@router.post("/ask")
def ask(request: PromptRequest):
    response = ask_claude(request.prompt)
    return {"response": response}
