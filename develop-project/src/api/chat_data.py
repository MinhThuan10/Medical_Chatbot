from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from src.database import get_db
from src.models_llm import ChatDataModel
from src.models.chat_data import Chat_data

templates = Jinja2Templates(directory="templates")

router = APIRouter(
    prefix="/chat_data",
    tags=["chat_data"]
)

@router.post("/{conservation_id}")
async def insert_chat_data(
    request: Request,
    conservation_id: int,
    db: Session = Depends(get_db)
):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return {"error": "User ID not found in cookies"}
    data = await request.json()
    question_text = data.get("question_text")
    answer_text = ChatDataModel().model(question_text)
    print(f"User ID: {user_id}, Conservation ID: {conservation_id}, Question: {question_text}, Answer: {answer_text}")
    if answer_text:
        chat_data = Chat_data().insert_chat_data(
            db=db,
            user_id=user_id,
            conservation_id=conservation_id,
            question_text=question_text,
            answer_text=answer_text
        )
    return chat_data