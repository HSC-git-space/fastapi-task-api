import bcrypt
from datetime import datetime, timedelta
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models import BlacklistedToken

SECRET_KEY = "change-this-later-to-something-random"
ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def create_access_token(data: dict, expires_minutes: int = 30):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        user_id = payload.get("user_id")
        if username is None or user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"username": username, "user_id": user_id}
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def create_refresh_token(data: dict, expires_days: int = 7):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=expires_days)
    to_encode.update({"exp": expire, "jti": str(uuid.uuid4()), "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def is_blacklisted(jti: str, db: AsyncSession) -> bool:
    result = await db.execute(select(BlacklistedToken).where(BlacklistedToken.jti == jti))
    return result.scalar_one_or_none() is not None

async def verify_refresh_token(token: str, db: AsyncSession):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")

    jti = payload.get("jti")
    if await is_blacklisted(jti, db):
        raise HTTPException(status_code=401, detail="Refresh token has been revoked")

    return payload