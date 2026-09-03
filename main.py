from typing import Optional
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select
from auth import hash_password, verify_password, create_access_token, get_current_user
from database import engine, SessionLocal, Base
import models
import asyncio

app = FastAPI()

class TaskCreate(BaseModel):
    title: str
    completed: bool = False
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

@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with SessionLocal() as db:
        yield db

@app.get("/slow-demo")
async def slow_demo():
    print("Starting the slow operation...")
    await asyncio.sleep(5)
    print("Done waiting.")
    return {"message": "This took 5 seconds but didn't block anything else"}

@app.post("/users", response_model=UserOut)
async def create_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    hashed = hash_password(user.password)
    new_user = models.User(username=user.username, hush_hush=hashed)
    db.add(new_user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Username already taken")
    await db.refresh(new_user)
    return new_user

@app.get("/users/{user_id}", response_model=UserOut)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.User).filter(models.User.id == user_id))
    user = result.scalars().first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.post("/login")
async def login(credentials: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.User).filter(models.User.username == credentials.username))
    user = result.scalars().first()
    if user is None or not verify_password(credentials.password, user.hush_hush):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    token = create_access_token({"sub": user.username, "user_id": user.id})
    return {"access_token": token, "token_type": "bearer"}

@app.post("/tasks")
async def create_task(task: TaskCreate, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    new_task = models.Task(
        title=task.title,
        completed=task.completed,
        user_id=current_user["user_id"],
        description=task.description,
    )
    db.add(new_task)
    await db.commit()
    await db.refresh(new_task)
    return new_task

@app.get("/tasks")
async def get_tasks(db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    result = await db.execute(select(models.Task).filter(models.Task.user_id == current_user["user_id"]))
    return result.scalars().all()

@app.get("/tasks/{task_id}")
async def get_task(task_id: int, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    result = await db.execute(select(models.Task).filter(models.Task.id == task_id))
    task = result.scalars().first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.user_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Not authorized to view this task")
    return task

@app.patch("/tasks/{task_id}")
async def update_task(task_id: int, updates: TaskUpdate, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    result = await db.execute(select(models.Task).filter(models.Task.id == task_id))
    task = result.scalars().first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.user_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Not authorized to modify this task")
    if updates.title is not None:
        task.title = updates.title
    if updates.completed is not None:
        task.completed = updates.completed
    await db.commit()
    await db.refresh(task)
    return task

@app.delete("/tasks/{task_id}")
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    result = await db.execute(select(models.Task).filter(models.Task.id == task_id))
    task = result.scalars().first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.user_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Not authorized to delete this task")
    await db.delete(task)
    await db.commit()
    return {"message": "Task deleted"}