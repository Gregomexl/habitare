"""Password hashing using Argon2id (argon2-cffi).

Uses argon2-cffi defaults: time_cost=2, memory_cost=65536 (64 MiB), parallelism=1.
These produce ~97-character output, well within the TEXT column.
"""
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError

_ph = PasswordHasher()


def hash_password(password: str) -> str:
    """Return an Argon2id hash of password."""
    return _ph.hash(password)


def verify_password(password: str, hash: str) -> bool:
    """Return True if password matches hash. Never raises — returns False on any error."""
    if not hash:
        return False
    try:
        _ph.verify(hash, password)
        return True
    except (VerifyMismatchError, InvalidHashError):
        return False
