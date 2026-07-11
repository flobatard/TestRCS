from typing import Any

from pydantic import BaseModel


class MeRead(BaseModel):
    sub: str
    email: str | None
    roles: list[str]
    claims: dict[str, Any]
