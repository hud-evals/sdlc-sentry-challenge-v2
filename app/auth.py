from fastapi import Depends, Request, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.config import AUTH_ENABLED


def get_current_user(request: Request, db: Session = Depends(get_db)):
    if not AUTH_ENABLED:
        return None

    user_id = request.headers.get("X-User-Id")
    if not user_id:
        return None

    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        return None

    user = db.query(User).filter(User.id == user_id).first()
    return user


def require_auth(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


# BUG 6: reads request.state.user_role but middleware sets request.state.role
def require_write_permission(request: Request):
    try:
        role = request.state.role
    except AttributeError:
        raise HTTPException(status_code=403, detail="Permission denied")

    if role not in ("admin", "manager", "member"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return True
