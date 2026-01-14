from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.src.core.database import get_db
from app.src.services.langchains import rag
from app.src.services.service_chatdata import Chat_data


templates = Jinja2Templates(directory="templates")
router = APIRouter(
    prefix="/chat_data",
    tags=["chat_data"]
)

@router.post("/{conservation_id}")
async def answer_question(
    request: Request,
    conservation_id: int,
):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return {"error": "User ID not found in cookies"}
    data = await request.json()
    question_text = data.get("question_text")

    return rag.chat(question_text, chat_id=conservation_id)

@router.post("/insert/{conservation_id}")
async def answer_question(
    request: Request,
    conservation_id: int,
    db: Session = Depends(get_db)
):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return {"error": "User ID not found in cookies"}
    data = await request.json()
    question_text = data.get("question_text")
    answer_text = data.get("answer_text")
    if answer_text:
        chat_data = Chat_data().insert_chat_data(
            db=db,
            user_id=user_id,
            conservation_id=conservation_id,
            question_text=question_text,
            answer_text=answer_text
        )

        rag.save_menory(
            memory=rag.get_memory(conservation_id),
            question=question_text,
            answer=answer_text)
    return chat_data