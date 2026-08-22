from typing import Optional
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from auth import hash_password, verify_password, create_access_token, get_current_user

from database import engine, SessionLocal, Base
import models

Base.metadata.create_all(bind=engine)

app = FastAPI()

class TaskCreate(BaseModel):
    title: str
    completed: bool = False
    user_id: int
    description: Optional[str] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    completed: Optional[bool] = None

class UserCreate(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class UserOut(BaseModel):
    id: int
    username: str

    class Config:
        from_attributes = True

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/users", response_model=UserOut)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    hashed = hash_password(user.password)
    new_user = models.User(username=user.username, hush_hush=hashed)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.post("/login")
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == credentials.username).first()
    if user is None or not verify_password(credentials.password, user.hush_hush):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    token = create_access_token({"sub": user.username, "user_id": user.id})
    return {"access_token": token, "token_type": "bearer"}

@app.post("/tasks")
def create_task(task: TaskCreate, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    new_task = models.Task(title=task.title, completed=task.completed, user_id=task.user_id, description=task.description)
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return new_task

@app.get("/tasks")
def get_tasks(db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    return db.query(models.Task).all()

@app.get("/tasks/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@app.patch("/tasks/{task_id}")
def update_task(task_id: int, updates: TaskUpdate, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if updates.title is not None:
        task.title = updates.title
    if updates.completed is not None:
        task.completed = updates.completed
    db.commit()
    db.refresh(task)
    return task

@app.delete("/tasks/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
    return {"message": "Task deleted"}