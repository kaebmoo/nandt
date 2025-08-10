from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from core.database import Base

class Organization(Base):
    __tablename__ = "organizations"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    cal_com_api_key = Column(String, nullable=True) # API Key from Cal.com
    stripe_customer_id = Column(String, unique=True, nullable=True)
    users = relationship("User", back_populates="organization")