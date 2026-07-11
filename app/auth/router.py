from fastapi import APIRouter, Depends

from app.auth.schemas import MeRead
from app.core.auth import AuthenticatedUser, get_current_user

router = APIRouter(tags=["auth"])


@router.get("/me", response_model=MeRead)
async def read_me(user: AuthenticatedUser = Depends(get_current_user)) -> MeRead:
    """Demo protected route: returns the authenticated user's identity."""
    return MeRead(
        sub=user.sub,
        email=user.email,
        roles=sorted(user.roles),
        claims=user.claims,
    )
