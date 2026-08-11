from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import json
from app.src.core.database import get_db
from app.src.services.langchains_graphRAG import GraphRAG
from app.src.services.service_chatdata import Chat_data
from app.src.schemas.chat_data import Request_Chat_data, Request_Import_Chat_data, Response_Import_Chat_data

templates = Jinja2Templates(directory="templates")
router = APIRouter(
    prefix="/chat_data",
    tags=["chat_data"]
)

@router.post("/{conservation_id}", response_class=StreamingResponse)
async def answer_question(
    request: Request,
    req_data: Request_Chat_data,
    conservation_id: int,
):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return {"error": "User ID not found in cookies"}
    question_text = req_data.question_text

    return GraphRAG.chat(question_text, chat_id=conservation_id)

@router.post("/insert/{conservation_id}", response_model=Response_Import_Chat_data)
async def answer_question(
    request: Request,
    req_data: Request_Import_Chat_data,
    conservation_id: int,
    db: Session = Depends(get_db)
):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return {"error": "User ID not found in cookies"}
    question_text = req_data.question_text
    answer_text = req_data.answer_text

    clean_answer = ""
    citations_json = []

    if answer_text:
        chunk_map = GraphRAG.get_chunk_memory(conservation_id)
        clean_answer, citations_json = GraphRAG.parse_answer_and_citations(
            answer_text,
            chunk_map
        )
        # print(chunk_map)
        chat_data = Chat_data().insert_chat_data(
            db=db,
            user_id=user_id,
            conservation_id=conservation_id,
            question_text=question_text,
            answer_text=clean_answer,
            citations_json=citations_json,
        )

        GraphRAG.save_menory(
            memory=GraphRAG.get_memory(conservation_id),
            question=question_text,
            answer=answer_text)
    return {
        "chat_id": chat_data,
        "answer_text": clean_answer,
        "citations_json": json.dumps(citations_json, ensure_ascii=False)
    }