"""
MVP版 認証ルーター
デモユーザー（id=1）のみ対応
"""
from fastapi import APIRouter, Depends
from datetime import datetime, timedelta
from jose import jwt
from ..config import get_settings
from ..schemas import TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def create_access_token(user_id: int) -> str:
    """JWTアクセストークンを生成"""
    expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "exp": expire
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


@router.post("/demo-login", response_model=TokenResponse)
def demo_login():
    """
    デモユーザーとしてログイン
    パスワード不要、固定ユーザー（id=1）のJWTを返す
    """
    token = create_access_token(user_id=1)
    return TokenResponse(access_token=token)
