from sqlalchemy import Column, Integer, String, ForeignKey, Table
from database import Base

# Association table for users in groups
user_groups = Table(
    'user_groups',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('group_id', Integer, ForeignKey('groups.id'), primary_key=True),
    Column('role', String, default='member')  # 'admin' or 'member'
)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)
    password = Column(String)
    security_question = Column(String)
    security_answer = Column(String)

class Group(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(String)  # Store as string for simplicity

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