from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from src.database import get_db
from src.models.chat_data import chat_data_class
from src.langchains import rag

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
    all_chat_data = chat_data_class.get_all_chat_data(user_id, conservation_id, db=db)

    # history_chat insert to memory
    latest_chats = sorted(all_chat_data, key=lambda x: x['stt'], reverse=True)[:5]

    memory = rag.get_memory(conservation_id)
    history = memory.load_memory_variables({}).get("chat_history", "")

    if not history:
        print("❌ Chưa có gì trong memory")
        for chat in reversed(latest_chats):
            rag.save_menory(
                memory=memory,
                question=chat['question_text'],
                answer=chat['answer_text']
            )
    else:
        print("✅ Có dữ liệu memory:")
        print(history)


    response = templates.TemplateResponse("index.html", {
        "request": request,
        "chat_data": all_chat_data,
        "msg": msg
    })

    response.set_cookie(
        key="user_id",
        value=user_id,
        httponly=False,
        max_age=60*60*24*30 
    )

    return response
