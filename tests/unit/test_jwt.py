import uuid
import pytest
from fastapi import HTTPException
from app.core.jwt import create_access_token, decode_token


TENANT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def test_encode_decode_roundtrip():
    token = create_access_token(USER_ID, TENANT_ID, "tenant_user")
    payload = decode_token(token)
    assert payload["sub"] == str(USER_ID)
    assert payload["tenant_id"] == str(TENANT_ID)
    assert payload["role"] == "tenant_user"


def test_decode_expired_token_raises_401():
    token = create_access_token(USER_ID, TENANT_ID, "tenant_user", expire_minutes=-1)
    with pytest.raises(HTTPException) as exc:
        decode_token(token)
    assert exc.value.status_code == 401


def test_decode_tampered_token_raises_401():
    token = create_access_token(USER_ID, TENANT_ID, "tenant_user")
    tampered = token[:-5] + "XXXXX"
    with pytest.raises(HTTPException) as exc:
        decode_token(tampered)
    assert exc.value.status_code == 401


def test_decode_missing_claims_raises_401():
    import jwt as pyjwt
    from app.core.config import settings
    payload = {"sub": str(USER_ID), "role": "tenant_user"}
    token = pyjwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
    with pytest.raises(HTTPException) as exc:
        decode_token(token)
    assert exc.value.status_code == 401
