"""User endpoints: profile retrieval and management."""
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import AsyncSessionDep, CurrentUserDep, RequireAdminDep, set_rls
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.schemas.user import (
    UserCreate,
    UserCreateResponse,
    UserResponse,
    UserUpdate,
    UserUpdateMe,
)

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


@router.put("/me", response_model=UserResponse)
async def update_me(
    body: UserUpdateMe,
    current_user: CurrentUserDep,
    db: AsyncSessionDep,
) -> UserResponse:
    """Update the authenticated user's own profile."""
    async with db.begin():
        await set_rls(db, current_user.tenant_id)
        result = await db.execute(select(User).where(User.id == current_user.user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if body.full_name is not None:
            user.full_name = body.full_name
        if body.phone_number is not None:
            user.phone_number = body.phone_number
        if body.unit_number is not None:
            user.unit_number = body.unit_number
        user.updated_at = datetime.now(timezone.utc)

    return UserResponse.model_validate(user)


@router.get("/", response_model=list[UserResponse])
async def list_users(
    current_user: RequireAdminDep,
    db: AsyncSessionDep,
    limit: int = 50,
    offset: int = 0,
) -> list[UserResponse]:
    """List all users in the caller's tenant. Requires PROPERTY_ADMIN or SUPER_ADMIN."""
    async with db.begin():
        await set_rls(db, current_user.tenant_id)
        result = await db.execute(
            select(User)
            .order_by(User.created_at.desc())
            .limit(min(limit, 200))
            .offset(offset)
        )
        users = result.scalars().all()
    return [UserResponse.model_validate(u) for u in users]


@router.post("/", response_model=UserCreateResponse, status_code=201)
async def create_user(
    body: UserCreate,
    current_user: RequireAdminDep,
    db: AsyncSessionDep,
) -> UserCreateResponse:
    """Create a staff account. Returns a one-time temp password. Requires PROPERTY_ADMIN+."""
    if body.role == UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=422, detail="Cannot create SUPER_ADMIN accounts via API")

    temp_password = secrets.token_urlsafe(12)
    pw_hash = hash_password(temp_password)

    new_user = User(
        tenant_id=current_user.tenant_id,
        email=body.email,
        password_hash=pw_hash,
        full_name=body.full_name,
        phone_number=body.phone_number,
        unit_number=body.unit_number,
        role=body.role,
        is_active=True,
        email_verified=False,
    )

    try:
        async with db.begin():
            await set_rls(db, current_user.tenant_id)
            db.add(new_user)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Email already registered in this property")

    # model_validate on the ORM object gives us all UserResponse fields;
    # then inject temp_password (not stored on the model) for the one-time response.
    return UserCreateResponse(
        **UserResponse.model_validate(new_user).model_dump(),
        temp_password=temp_password,
    )


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    current_user: RequireAdminDep,
    db: AsyncSessionDep,
) -> UserResponse:
    """Update a user in the caller's tenant. Requires PROPERTY_ADMIN+."""
    # Self-edit guard first: /me has no role field so SUPER_ADMIN escalation is impossible that way.
    if user_id == current_user.user_id:
        raise HTTPException(
            status_code=400, detail="Use PUT /users/me to update your own profile"
        )

    if body.role == UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=422, detail="Cannot assign SUPER_ADMIN role via API")

    async with db.begin():
        await set_rls(db, current_user.tenant_id)
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if body.full_name is not None:
            user.full_name = body.full_name
        if body.phone_number is not None:
            user.phone_number = body.phone_number
        if body.unit_number is not None:
            user.unit_number = body.unit_number
        if body.is_active is not None:
            user.is_active = body.is_active
        if body.role is not None:
            user.role = body.role
        user.updated_at = datetime.now(timezone.utc)

    return UserResponse.model_validate(user)
