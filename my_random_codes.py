from sqlalchemy import create_engine, text, Float, Integer, String, Column 
from sqlalchemy.ext.declarative import declarative_base 
import pandas as pd

from pydantic import BaseModel, EmailStr, Field
from pydantic_settings import BaseSettings 

from typing import Optional

#python data class 
class User(BaseModel):
    id: int 
    name: str = Field(..., min_length = 1, max_length = 20)
    rate: float = Field(..., ge = 0, le = 1000)
    hours: float = Field(..., gt = 0, lt = 1000)
    salary: float = Field(..., ge = 0)
    Email: Optional[EmailStr] = Field(None)

#.xml config loader
class XmlConfigLoader(BaseSettings):
    connection_url: str 
    class Config:
        env_file = "config.xml"

import xml.etree.ElementTree as ET 

def xml_config_parser(xml_file_path: str):
    try:
        tree = ET.parse(xml_file_path)
        root = tree.getroot()
        config = {}

        database_config = root.find('database')
        config['database'] ={
            'connection_url': database_config.find('connection_url')
        }
        return config 
    except FileNotFoundError:
        print("")
    except ET.ParseError:
        print("")
    except Exception as e:
        print("")

#database connection: sqlalchemy 

engine = create_engine("connection_url")

query = "UPDATE employee SET name ='bing' WHERE id =1; SELECT * FROM table_name WHERE condition; INSERT..."
with engine.connect() as conn:
    result = conn.execute(text(query))
    rows = result.fetchall()
    columns = result.keys()

df = pd.read_sql(query, engine)

#sqlalchemy orm:
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()
local_session = sessionmaker()

class User(Base):
    id = Column(Integer, primary_key = True, index = True)
    name = Column(String)
    rate = Column(Float)
    hours = Column(Float)
    salary = Column(Float)
    email = Column(String)

#fastapi main script 
from fastapi import FastAPI, Depends
from sqlalchemy.orm import session
from pydantic import Depends

app = FastAPI(title = "", version = "1.0.0")
users =[{}, {}]

Base.metadata.create_all(engine) #asynchronous use Base.metadata.create_all without binding engine

#Depends injection
def get_db():
    db = local_session()
    try:
        yield db 
    finally:
        db.close()

def db_init(db: session = Depends(get_db)):
    count = db.query(User).count()
    if count == 0:
        for user in users:
            db.add(User(**user))
        db.commit()
    return {"error msg"}

@app.get("/")
def root():
    return {"Welcome!"}

@app.post("/users")
def all_users(db: session = Depends(get_db)):
    db_users = db.query(User).all()
    return db_users

#run server: uvicorn main:app --host localhost --port 8000
#swagger doxc: localhost:8000/docs