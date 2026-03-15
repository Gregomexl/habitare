# tests/unit/test_require_role.py
import uuid
import pytest
from fastapi import HTTPException

from app.api.deps import TokenData, require_role
from app.models.user import UserRole


def _token(role: UserRole) -> TokenData:
    return TokenData(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), role=role)


@pytest.mark.asyncio
async def test_correct_role_passes():
    check = require_role(UserRole.PROPERTY_ADMIN)
    result = await check(_token(UserRole.PROPERTY_ADMIN))
    assert result.role == UserRole.PROPERTY_ADMIN


@pytest.mark.asyncio
async def test_wrong_role_raises_403():
    check = require_role(UserRole.PROPERTY_ADMIN)
    with pytest.raises(HTTPException) as exc:
        await check(_token(UserRole.TENANT_USER))
    assert exc.value.status_code == 403
    assert exc.value.detail == "Insufficient permissions"


@pytest.mark.asyncio
async def test_super_admin_passes_admin_guard():
    check = require_role(UserRole.PROPERTY_ADMIN, UserRole.SUPER_ADMIN)
    result = await check(_token(UserRole.SUPER_ADMIN))
    assert result.role == UserRole.SUPER_ADMIN


@pytest.mark.asyncio
async def test_super_admin_only_guard():
    check = require_role(UserRole.SUPER_ADMIN)
    result = await check(_token(UserRole.SUPER_ADMIN))
    assert result.role == UserRole.SUPER_ADMIN


@pytest.mark.asyncio
async def test_property_admin_fails_super_admin_guard():
    check = require_role(UserRole.SUPER_ADMIN)
    with pytest.raises(HTTPException) as exc:
        await check(_token(UserRole.PROPERTY_ADMIN))
    assert exc.value.status_code == 403
