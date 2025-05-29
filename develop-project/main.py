from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, Response
from fastapi import Request
from fastapi.staticfiles import StaticFiles
import uuid
from src.models.users import Users
from datetime import datetime
from src.database import get_db
from src.api import conservation, chat_data, chat

app = FastAPI()

app.include_router(conservation.router)
app.include_router(chat_data.router)
app.include_router(chat.router)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):

    cookies = request.cookies
    user_id = cookies.get("user_id")
    if not user_id:
        user_id = str(uuid.uuid4())
        db = next(get_db())
        Users().create_user(db,
            user_id=user_id,
            create_at=datetime.now(),
            last_seen=datetime.now()
        )
        msg = "Create new session"
    else:
        msg = "Hello from Chatbot"
    
    db = next(get_db())
    Users().update_user(db,
            user_id=user_id,
            last_seen=datetime.now()
        )
    response = templates.TemplateResponse("index.html", {"request": request, "chat_data": None, "msg": msg})
    response.set_cookie(
        key="user_id",
        value=user_id,
        httponly=False,
        max_age=60*60*24*30 
    )

    return response

