TASK_STATUSES = ["open", "in_progress", "in_review", "done", "cancelled"]
TASK_PRIORITIES = ["critical", "high", "medium", "low"]
USER_ROLES = ["admin", "manager", "member", "viewer"]

ALLOWED_SORT_FIELDS = ["created_at", "updated_at", "priority", "status", "title"]

PRIORITY_WEIGHTS = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}
