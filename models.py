from sqlalchemy import Column, Integer, String, ForeignKey
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)
    password = Column(String)
    security_question = Column(String)
    security_answer = Column(String)

class Match(Base):
    __tablename__ = "matches"
    id = Column(Integer, primary_key=True, index=True)
    team_1 = Column(String)
    team_2 = Column(String)
    kickoff = Column(String)
    location = Column(String)
    score_1 = Column(Integer, nullable=True) # Official score
    score_2 = Column(Integer, nullable=True)

class Guess(Base):
    __tablename__ = "guesses"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    match_id = Column(Integer, ForeignKey("matches.id"))
    score_1 = Column(Integer)
    score_2 = Column(Integer)