from app.src.core.database import Base
from sqlalchemy import Column, String, Integer, ForeignKey


class Model_chat_data(Base):

    __tablename__ = "chat_data"
    __table_args__ = {'extend_existing': True} 
    chat_id = Column(Integer, primary_key=True, index=True)
    conservation_id = Column(Integer, ForeignKey("conservation.id"))
    question_text = Column(String(5000))
    answer_text = Column(String(1000))
    stt = Column(Integer)