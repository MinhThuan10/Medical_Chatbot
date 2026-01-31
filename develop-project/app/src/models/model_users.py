from app.src.core.database import Base
from sqlalchemy import Column, DateTime, String

class Users(Base):
    __tablename__ = "users"
    __table_args__ = {'extend_existing': True} 
    user_id = Column(String(255), primary_key=True, index=True)
    create_at = Column(DateTime)
    last_seen = Column(DateTime)