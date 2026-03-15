from app.core.security import hash_password, verify_password


def test_hash_password_returns_argon2_string():
    h = hash_password("secret")
    assert h.startswith("$argon2")


def test_verify_password_correct():
    h = hash_password("secret")
    assert verify_password("secret", h) is True


def test_verify_password_wrong():
    h = hash_password("secret")
    assert verify_password("wrong", h) is False


def test_verify_password_empty_hash_returns_false():
    assert verify_password("secret", "") is False
