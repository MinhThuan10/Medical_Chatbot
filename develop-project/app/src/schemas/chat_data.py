from pydantic import BaseModel

class Request_Chat_data(BaseModel):
    question_text: str

    
class Response_Chat_data(BaseModel):
    answer_text: str

class Request_Import_Chat_data(BaseModel):
    question_text: str
    answer_text: str

class Response_Import_Chat_data(BaseModel):
    chat_id: int