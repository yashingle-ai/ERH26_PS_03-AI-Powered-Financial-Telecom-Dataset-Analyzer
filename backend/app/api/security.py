"""Authentication & authorization (review fix C2).

JWT bearer auth with bcrypt-hashed passwords and role-based access control (RBAC).
Users are seeded from environment for the demo; a real deployment plugs a user store /
IdP behind `authenticate_user`. Secrets come from env — never hard-coded.

Env:
  ERAKSHAK_JWT_SECRET     signing secret (required in prod; ephemeral+warned if unset)
  ERAKSHAK_ADMIN_PASSWORD seed admin password (defaults to a random one, logged once)
  ERAKSHAK_ANALYST_PASSWORD seed analyst password
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from ..core.logging_config import audit, get_logger

log = get_logger(__name__)

ALGORITHM = "HS256"
TOKEN_TTL_MIN = int(os.getenv("ERAKSHAK_TOKEN_TTL_MIN", "60"))
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="v1/auth/token")


def _hash(password: str) -> bytes:
    # bcrypt directly (passlib 1.7 is incompatible with bcrypt>=4)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())


def _verify(password: str, hashed: bytes) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed)
    except ValueError:
        return False


def _secret() -> str:
    s = os.getenv("ERAKSHAK_JWT_SECRET")
    if not s:
        # ephemeral secret so tokens don't survive restart; loudly warn (dev only).
        s = getattr(_secret, "_ephemeral", None) or secrets.token_urlsafe(48)
        _secret._ephemeral = s
        log.warning("ERAKSHAK_JWT_SECRET not set — using an EPHEMERAL secret (dev only). "
                    "Set it in production.")
    return s


def _seed_users() -> dict:
    def mkpw(env, default_label):
        pw = os.getenv(env)
        if not pw:
            pw = secrets.token_urlsafe(12)
            log.warning("%s not set — generated a random %s password: %s",
                        env, default_label, pw)
        return _hash(pw)

    return {
        "admin": {"username": "admin", "hashed": mkpw("ERAKSHAK_ADMIN_PASSWORD", "admin"),
                  "roles": ["admin", "analyst"]},
        "analyst": {"username": "analyst",
                    "hashed": mkpw("ERAKSHAK_ANALYST_PASSWORD", "analyst"),
                    "roles": ["analyst"]},
    }


_USERS: dict | None = None


def _users() -> dict:
    global _USERS
    if _USERS is None:
        _USERS = _seed_users()
    return _USERS


def initialise_auth() -> None:
    """Resolve credentials and the JWT secret at boot rather than on first use.

    Both are lazy, and both warn when unset — a generated password, an ephemeral
    signing secret. Lazily, those warnings only appear once somebody tries to sign
    in, which is too late: behind compose nobody *can* sign in without first
    reading the generated password out of the log.

    Idempotent. `_users()` and `_secret()` both cache, so calling this and then
    authenticating will not reseed and invalidate what was just logged.
    """
    _users()
    _secret()


def authenticate_user(username: str, password: str) -> dict | None:
    u = _users().get(username)
    if not u or not _verify(password, u["hashed"]):
        return None
    return u


def create_access_token(username: str, roles: list[str]) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": username, "roles": roles, "iat": now,
               "exp": now + timedelta(minutes=TOKEN_TTL_MIN)}
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    cred_exc = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                             detail="Invalid or expired token",
                             headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, _secret(), algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise cred_exc
    username = payload.get("sub")
    if not username:
        raise cred_exc
    return {"username": username, "roles": payload.get("roles", [])}


def require_role(*roles: str):
    """Dependency factory enforcing that the user has at least one of `roles`."""
    async def _dep(user: dict = Depends(get_current_user)) -> dict:
        if roles and not (set(roles) & set(user.get("roles", []))):
            audit("access_denied", user=user["username"], need=list(roles))
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Insufficient role")
        return user
    return _dep
