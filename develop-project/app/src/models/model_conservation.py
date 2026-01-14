from app.src.core.database import Base
from sqlalchemy import Column, DateTime, String, Integer, ForeignKey


class Conservation(Base):

    __tablename__ = "conservation"
    __table_args__ = {'extend_existing': True} 
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(255), ForeignKey("users.user_id"))
    name = Column(String(255))
    create_day	 = Column(DateTime)
    chat_day = Column(DateTime)