from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from .database import get_db
from .models_db import User
from .auth import get_password_hash, verify_password, create_access_token
from pydantic import BaseModel
from sqlalchemy import select

router = APIRouter(prefix="/auth", tags=["认证"])

class RegisterRequest(BaseModel):
    email: str
    password: str
    role: str = "candidate"

class LoginRequest(BaseModel):
    email: str
    password: str

@router.post("/register")
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # 检查邮箱
    stmt = select(User).where(User.email == req.email)
    result = await db.execute(stmt)
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="邮箱已注册")
    
    # 密码长度检查 (字节)
    if len(req.password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="密码过长，请使用 72 字节以内的密码")
    
    user = User(
        email=req.email,
        password_hash=get_password_hash(req.password),
        role=req.role,
    )
    db.add(user)
    await db.commit()
    return {"msg": "注册成功", "user_id": str(user.id)}

@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    stmt = select(User).where(User.email == req.email)
    result = await db.execute(stmt)
    user = result.scalars().first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=400, detail="邮箱或密码错误")
    token = create_access_token(data={"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer", "role": user.role, "user_id": str(user.id)}
