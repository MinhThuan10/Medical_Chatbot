from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.src.core.database import get_db
from app.src.services.service_conservation import Conservation
from app.src.services.service_chatdata import Chat_data

from datetime import datetime


templates = Jinja2Templates(directory="templates")

router = APIRouter(
    prefix="/conservation",
    tags=["conservation"]
)

@router.get("/")
def get_all_conservations(request: Request, db: Session = Depends(get_db)):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return {"error": "User ID not found in cookies"}
    conservations = Conservation().get_all_conservations(user_id, db=db)
    grouped_temp = {}  # label -> (sort_key, [items])
    now = datetime.now()

    for conservation in conservations:
        chat_day = conservation.get("chat_day")
        if not chat_day:
            continue

        delta = now.date() - chat_day.date()

        if delta.days == 0:
            label = "Hôm nay"
            sort_key = 0
        elif delta.days == 1:
            label = "Hôm qua"
            sort_key = 1
        elif 2 <= delta.days < 7:
            label = chat_day.strftime("%d/%m/%Y")
            sort_key = delta.days  # 2 -> 6
        elif 7 <= delta.days <= 30:
            label = "1 tuần trước"
            sort_key = 31
        elif 30 < delta.days <= 365:
            label = "1 tháng trước"
            sort_key = 32
        elif delta.days > 365:
            label = "1 năm trước"
            sort_key = 33
        else:
            label = "Không rõ"
            sort_key = 99

        if label not in grouped_temp:
            grouped_temp[label] = (sort_key, [])

        grouped_temp[label][1].append({
            "id": conservation.get("id"),
            "name": conservation.get("name"),
            "chat_day": chat_day
        })

    sorted_items = sorted(grouped_temp.items(), key=lambda item: item[1][0])

    list_conservations = []
    for label, (_, items) in sorted_items:
        sorted_conservations = sorted(items, key=lambda x: x["chat_day"], reverse=True)
        cleaned_items = [
            {"id": item["id"], "name": item["name"]}
            for item in sorted_conservations
        ]
        list_conservations.append({"label": label, "items": cleaned_items})

    return {"list_conservations": list_conservations}

@router.post("/new")
async def create_conservation(request: Request, db: Session = Depends(get_db)):

    user_id = request.cookies.get("user_id")
    if not user_id:
        return {"error": "User ID not found in cookies"}
    
    data = await request.json()
    conversation_name = data.get("question_text").strip()[:50]
    conversation_id = Conservation().create_conservation(
        db=db,
        user_id=user_id,
        name=conversation_name,
        create_day=datetime.now(),
        chat_day=datetime.now(),
    )
    return {"message": "Conversation created", "conversation_id": conversation_id}

@router.put("/update/{conservation_id}")
async def update_conservation(request: Request, conservation_id: str, db: Session = Depends(get_db)):
    data = await request.json()
    user_id = request.cookies.get("user_id")
    if not user_id:
        return {"error": "User ID not found in cookies"}
    
    name = data.get("name")
    chat_day = datetime.now()
    if not conservation_id or not name:
        return {"error": "Missing required fields"}

    success = Conservation().update_conservation(
        db=db,
        user_id=user_id,
        conservation_id=conservation_id,
        name=name,
        chat_day=chat_day
    )
    
    if success:
        return {"message": "Conversation updated successfully"}
    else:
        return {"error": "Failed to update conversation"}
    

@router.delete("/delete/{conservation_id}")
async def delete_conservation(request: Request, conservation_id: str, db: Session = Depends(get_db)):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return {"error": "User ID not found in cookies"}
    
    if not conservation_id:
        return {"error": "Missing required fields"}
    success = Conservation().delete_conservation(
        db=db,
        user_id=user_id,
        conservation_id=conservation_id
    )
    
    if success:
        return {"message": "Conversation deleted successfully"}
    else:
        return {"error": "Failed to delete conversation"}
    

@router.get("/{conservation_id}")
async def get_conservation(request: Request, conservation_id: str, db: Session = Depends(get_db)):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return {"error": "User ID not found in cookies"}
    chat_data =Chat_data().get_all_chat_data(
        user_id=user_id,
        conservation_id=conservation_id,
        db=db
    )
        
    return {"conservation": chat_data}