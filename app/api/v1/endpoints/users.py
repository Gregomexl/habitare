"""User endpoints: profile retrieval."""
from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import AsyncSessionDep, CurrentUserDep, set_rls
from app.models.user import User
from app.schemas.user import UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUserDep, db: AsyncSessionDep) -> UserResponse:
    """Return the authenticated user's profile."""
    async with db.begin():
        await set_rls(db, current_user.tenant_id)
        result = await db.execute(select(User).where(User.id == current_user.user_id))
        user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return UserResponse.model_validate(user)
