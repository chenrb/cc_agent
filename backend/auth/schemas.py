"""auth / admin 路由的 Pydantic 请求与响应模型。"""

from pydantic import BaseModel


class LoginIn(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    username: str
    role: str


class LoginOut(BaseModel):
    user: UserOut
    expires_in: int


class CreateUserIn(BaseModel):
    username: str
    password: str
    role: str = "user"


class UpdateUserIn(BaseModel):
    is_active: bool | None = None
    role: str | None = None
    password: str | None = None
