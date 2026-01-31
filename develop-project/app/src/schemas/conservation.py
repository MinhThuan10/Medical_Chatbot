from pydantic import BaseModel

class item(BaseModel):
    id: int
    name: str 

class Conservation(BaseModel):
    label: str
    items: list[item]

class Respone_Conservation(BaseModel):
    list_conservations: list[Conservation]

class ConservationCreateRequest(BaseModel):
    question_text: str

class ConservationCreateResponse(BaseModel):
    message: str
    conversation_id: int

class ConservationUpdateRequest(BaseModel):
    conservation_name: str
    
class ConservationUpdateResponse(BaseModel):
    message: str

class ConservationDeleteResponse(BaseModel):
    message: str

class ConservationData(BaseModel):
    chat_id: int
    conservation_id: int
    question_text: str
    answer_text: str
    stt: int    

class ConservationDetailResponse(BaseModel):
    conservation: list[ConservationData]