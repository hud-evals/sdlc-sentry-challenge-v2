from sqlalchemy.orm import Session

from app.models import Task, AuditLog
from app.constants import PRIORITY_WEIGHTS


def calculate_task_score(task):
    weight = PRIORITY_WEIGHTS.get(task.priority, 1)
    if task.status == "done":
        return weight * 10
    if task.status == "in_progress":
        return weight * 5
    return weight


def get_overdue_tasks(db: Session):
    from datetime import datetime
    return db.query(Task).filter(
        Task.due_date < datetime.utcnow(),
        Task.status != "done",
        Task.status != "cancelled",
    ).all()


def log_action(db: Session, action: str, entity_type: str, entity_id: int, user_id=None, details=None):
    entry = AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        details=details,
    )
    db.add(entry)
    db.commit()
    return entry


def reassign_tasks(db: Session, from_user_id: int, to_user_id: int):
    tasks = db.query(Task).filter(Task.assigned_to == from_user_id).all()
    for task in tasks:
        task.assigned_to = to_user_id
    db.commit()
    return len(tasks)


def get_task_summary(db: Session, organization_id: int):
    tasks = db.query(Task).filter(Task.organization_id == organization_id).all()
    summary = {"total": len(tasks), "by_status": {}, "by_priority": {}}
    for task in tasks:
        status = task.status or "unknown"
        priority = task.priority or "unknown"
        summary["by_status"][status] = summary["by_status"].get(status, 0) + 1
        summary["by_priority"][priority] = summary["by_priority"].get(priority, 0) + 1
    return summary
