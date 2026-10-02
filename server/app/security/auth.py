"""Small bearer-token auth layer with stable principals and ownership checks."""

from __future__ import annotations

import hmac
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException

from app.config import settings


@dataclass(frozen=True)
class Principal:
    user_id: str


async def current_principal(authorization: str | None = Header(default=None)) -> Principal:
    if not settings.auth_required:
        return Principal("local")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer authentication required")
    supplied = authorization[7:]
    for token, user_id in settings.auth_token_map.items():
        if hmac.compare_digest(supplied, token):
            return Principal(user_id)
    raise HTTPException(status_code=401, detail="Invalid bearer token")


PrincipalDep = Depends(current_principal)


def require_owner(owner_id: str, principal: Principal) -> None:
    if owner_id != principal.user_id:
        # Deliberately hide existence of private resources.
        raise HTTPException(status_code=404, detail="Resource not found")
