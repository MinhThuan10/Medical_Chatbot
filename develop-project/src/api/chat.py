from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from src.database import get_db
from src.models_llm import ChatDataModel
from src.models.chat_data import Chat_data

templates = Jinja2Templates(directory="templates")

router = APIRouter(
    prefix="/chat",
    tags=["chat"]
)


@router.get("/{conservation_id}")
async def get_chat_data(
    request: Request,
    conservation_id: str,
    db: Session = Depends(get_db)
):
    user_id = request.cookies.get("user_id")
    if not user_id:
        msg = "Create new session"
        return {"error": "User ID not found in cookies"}
    else:
        msg = "Hello from Chatbot"
    chat_data = Chat_data().get_all_chat_data(user_id, conservation_id, db=db)
    # print(f"Chat data for conservation {conservation_id}: {chat_data}")
    response = templates.TemplateResponse("index.html", {
        "request": request,
        "chat_data": chat_data,
        "msg": msg
    })

    response.set_cookie(
        key="user_id",
        value=user_id,
        httponly=False,
        max_age=60*60*24*30 
    )

    return response
