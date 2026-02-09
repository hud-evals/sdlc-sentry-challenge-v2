from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Comment, Task
from app.schemas import CommentCreate, CommentResponse
from app.auth import require_write_permission

router = APIRouter(prefix="/comments", tags=["comments"])


@router.get("/", response_model=List[CommentResponse])
def list_comments(
    task_id: int = Query(...),
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    comments = (
        db.query(Comment)
        .filter(Comment.task_id == task_id)
        .order_by(Comment.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return comments


@router.post("/", response_model=CommentResponse, status_code=201)
def create_comment(
    comment: CommentCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_write_permission),
):
    task = db.query(Task).filter(Task.id == comment.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    from fastapi import Request

    new_comment = Comment(
        content=comment.content,
        task_id=comment.task_id,
        user_id=1,
    )
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)
    return new_comment


@router.delete("/{comment_id}", status_code=204)
def delete_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_write_permission),
):
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    db.delete(comment)
    db.commit()
