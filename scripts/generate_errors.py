#!/usr/bin/env python3
"""Generate realistic Sentry error events for the v2 challenge.

Sends events directly to the Sentry store API to simulate production errors
from each of the 6 bug types + 2 red herrings.

Usage:
    python scripts/generate_errors.py
"""
import json
import time
import uuid
import random
import requests
from datetime import datetime, timezone, timedelta

SENTRY_DSN = "http://68a9455040af31bae575671465c10918@localhost:8000/3"
# Parse DSN
DSN_KEY = "68a9455040af31bae575671465c10918"
STORE_URL = "http://localhost:8000/api/3/store/"

HEADERS = {
    "Content-Type": "application/json",
    "X-Sentry-Auth": f"Sentry sentry_version=7, sentry_key={DSN_KEY}",
}


def send_event(event):
    """Send a single event to Sentry store API."""
    event.setdefault("event_id", uuid.uuid4().hex)
    event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    event.setdefault("platform", "python")
    event.setdefault("sdk", {"name": "sentry.python.fastapi", "version": "1.39.1"})
    event.setdefault("server_name", "task-tracker-api-7f8b9c")
    event.setdefault("environment", "production")
    event.setdefault("release", "task-tracker@0.2.0")
    event.setdefault("contexts", {
        "runtime": {"name": "CPython", "version": "3.11.7"},
        "os": {"name": "Linux", "version": "6.1.0"},
    })

    resp = requests.post(STORE_URL, headers=HEADERS, json=event, timeout=10)
    if resp.status_code == 200:
        return True
    else:
        print(f"  FAILED ({resp.status_code}): {resp.text[:200]}")
        return False


# ============================================================================
# Bug 1: ProgrammingError - column tasks.priority does not exist
# (Alembic env var mismatch → migrations not applied to Postgres)
# ============================================================================

def generate_bug1_errors(count=30):
    print(f"Bug 1: ProgrammingError (priority column) x{count}")

    endpoints = [
        ("GET", "/api/v1/tasks/", "list_tasks"),
        ("GET", "/api/v1/tasks/1", "get_task"),
        ("POST", "/api/v1/tasks/", "create_task"),
        ("PATCH", "/api/v1/tasks/1", "update_task"),
        ("GET", "/api/v1/tasks/?priority=high", "list_tasks"),
    ]

    sql_variants = [
        ("SELECT tasks.id AS tasks_id, tasks.title AS tasks_title, tasks.description AS tasks_description, "
         "tasks.status AS tasks_status, tasks.priority AS tasks_priority, tasks.due_date AS tasks_due_date, "
         "tasks.assigned_to AS tasks_assigned_to, tasks.organization_id AS tasks_organization_id, "
         "tasks.created_at AS tasks_created_at, tasks.updated_at AS tasks_updated_at \n"
         "FROM tasks \n LIMIT %(param_1)s OFFSET %(param_2)s"),
        ("SELECT tasks.id AS tasks_id, tasks.title AS tasks_title, tasks.description AS tasks_description, "
         "tasks.status AS tasks_status, tasks.priority AS tasks_priority, tasks.due_date AS tasks_due_date, "
         "tasks.assigned_to AS tasks_assigned_to, tasks.organization_id AS tasks_organization_id, "
         "tasks.created_at AS tasks_created_at, tasks.updated_at AS tasks_updated_at \n"
         "FROM tasks \nWHERE tasks.id = %(id_1)s \n LIMIT %(param_1)s"),
    ]

    for i in range(count):
        method, path, func = random.choice(endpoints)
        sql = random.choice(sql_variants)
        event = {
            "logger": "app.middleware",
            "level": "error",
            "transaction": path,
            "tags": {
                "url": f"http://localhost:8001{path}",
                "method": method,
                "status_code": "500",
                "transaction": path,
            },
            "request": {
                "url": f"http://localhost:8001{path}",
                "method": method,
                "headers": {"Host": "localhost:8001", "User-Agent": "python-httpx/0.25.2"},
            },
            "exception": {
                "values": [
                    {
                        "type": "UndefinedColumn",
                        "value": (
                            "column tasks.priority does not exist\n"
                            "LINE 1: ...tasks_status, tasks.prio...\n"
                            "                                     ^\n"
                        ),
                        "module": "psycopg2.errors",
                        "mechanism": {"type": "logging", "handled": True},
                        "stacktrace": {
                            "frames": [
                                {
                                    "filename": "sqlalchemy/engine/base.py",
                                    "module": "sqlalchemy.engine.base",
                                    "function": "_exec_single_context",
                                    "lineno": 1969,
                                    "in_app": False,
                                    "context_line": "                    self.dialect.do_execute(",
                                },
                                {
                                    "filename": "sqlalchemy/engine/default.py",
                                    "module": "sqlalchemy.engine.default",
                                    "function": "do_execute",
                                    "lineno": 922,
                                    "in_app": False,
                                    "context_line": "        cursor.execute(statement, parameters)",
                                },
                            ],
                        },
                    },
                    {
                        "type": "ProgrammingError",
                        "value": (
                            f"(psycopg2.errors.UndefinedColumn) column tasks.priority does not exist\n"
                            f"LINE 1: ...tasks_status, tasks.prio...\n"
                            f"                                     ^\n\n"
                            f"[SQL: {sql}]\n"
                            f"(Background on this error at: https://sqlalche.me/e/20/f405)"
                        ),
                        "module": "sqlalchemy.exc",
                        "mechanism": {"type": "logging", "handled": True},
                        "stacktrace": {
                            "frames": [
                                {
                                    "filename": "app/middleware.py",
                                    "absPath": "/app/app/middleware.py",
                                    "module": "app.middleware",
                                    "function": "dispatch",
                                    "lineno": 52,
                                    "in_app": True,
                                    "context_line": "            response = await call_next(request)",
                                },
                                {
                                    "filename": "starlette/middleware/base.py",
                                    "module": "starlette.middleware.base",
                                    "function": "call_next",
                                    "lineno": 84,
                                    "in_app": False,
                                    "context_line": "                    raise app_exc",
                                },
                                {
                                    "filename": f"app/routers/tasks.py",
                                    "absPath": f"/app/app/routers/tasks.py",
                                    "module": "app.routers.tasks",
                                    "function": func,
                                    "lineno": 30 if func == "list_tasks" else 58,
                                    "in_app": True,
                                    "context_line": "    tasks = query.offset(skip).limit(limit).all()" if func == "list_tasks" else "    task = db.query(Task).filter(Task.id == task_id).first()",
                                },
                            ],
                        },
                    },
                ],
            },
            "fingerprint": ["bug1-programming-error-priority"],
        }
        ok = send_event(event)
        if i == 0:
            print(f"  {'OK' if ok else 'FAIL'}")
        time.sleep(0.1)

    print(f"  Sent {count} events")


# ============================================================================
# Bug 2: DataError - invalid input syntax for type timestamp: "not_set"
# (Migration 004 has bad server_default on DateTime column)
# ============================================================================

def generate_bug2_errors(count=15):
    print(f"Bug 2: DataError (due_date server_default) x{count}")

    for i in range(count):
        event = {
            "logger": "app.middleware",
            "level": "error",
            "transaction": "/api/v1/tasks/",
            "tags": {
                "url": "http://localhost:8001/api/v1/tasks/",
                "method": "POST",
                "status_code": "500",
            },
            "request": {
                "url": "http://localhost:8001/api/v1/tasks/",
                "method": "POST",
                "data": json.dumps({"title": "New task", "organization_id": 1, "priority": "high"}),
                "headers": {"Host": "localhost:8001", "Content-Type": "application/json"},
            },
            "exception": {
                "values": [
                    {
                        "type": "InvalidTextRepresentation",
                        "value": (
                            'invalid input syntax for type timestamp without time zone: "not_set"\n'
                        ),
                        "module": "psycopg2.errors",
                        "mechanism": {"type": "logging", "handled": True},
                        "stacktrace": {
                            "frames": [
                                {
                                    "filename": "sqlalchemy/engine/base.py",
                                    "module": "sqlalchemy.engine.base",
                                    "function": "_exec_single_context",
                                    "lineno": 1969,
                                    "in_app": False,
                                },
                                {
                                    "filename": "sqlalchemy/engine/default.py",
                                    "module": "sqlalchemy.engine.default",
                                    "function": "do_execute",
                                    "lineno": 922,
                                    "in_app": False,
                                },
                            ],
                        },
                    },
                    {
                        "type": "DataError",
                        "value": (
                            '(psycopg2.errors.InvalidTextRepresentation) invalid input syntax for type '
                            'timestamp without time zone: "not_set"\n\n'
                            "[SQL: INSERT INTO tasks (title, description, status, priority, due_date, "
                            "assigned_to, organization_id, created_at, updated_at) VALUES "
                            "(%(title)s, %(description)s, %(status)s, %(priority)s, DEFAULT, "
                            "%(assigned_to)s, %(organization_id)s, %(created_at)s, %(updated_at)s) "
                            "RETURNING tasks.id]\n"
                            "[parameters: {'title': 'New task', 'description': None, 'status': 'open', "
                            "'priority': 'high', 'assigned_to': None, 'organization_id': 1, "
                            "'created_at': '2026-02-08 10:30:00', 'updated_at': '2026-02-08 10:30:00'}]\n"
                            "(Background on this error at: https://sqlalche.me/e/20/9h9h)"
                        ),
                        "module": "sqlalchemy.exc",
                        "mechanism": {"type": "logging", "handled": True},
                        "stacktrace": {
                            "frames": [
                                {
                                    "filename": "app/middleware.py",
                                    "absPath": "/app/app/middleware.py",
                                    "module": "app.middleware",
                                    "function": "dispatch",
                                    "lineno": 52,
                                    "in_app": True,
                                    "context_line": "            response = await call_next(request)",
                                },
                                {
                                    "filename": "app/routers/tasks.py",
                                    "absPath": "/app/app/routers/tasks.py",
                                    "module": "app.routers.tasks",
                                    "function": "create_task",
                                    "lineno": 49,
                                    "in_app": True,
                                    "context_line": "    db.commit()",
                                },
                            ],
                        },
                    },
                ],
            },
            "fingerprint": ["bug2-dataerror-due-date-not-set"],
        }
        ok = send_event(event)
        if i == 0:
            print(f"  {'OK' if ok else 'FAIL'}")
        time.sleep(0.1)

    print(f"  Sent {count} events")


# ============================================================================
# Bug 3: ProgrammingError - relation "comments" does not exist
# (Migration 005 has typo in index column → migration fails)
# ============================================================================

def generate_bug3_errors(count=8):
    print(f"Bug 3: ProgrammingError (comments table) x{count}")

    for i in range(count):
        event = {
            "logger": "app.middleware",
            "level": "error",
            "transaction": "/api/v1/comments/",
            "tags": {
                "url": "http://localhost:8001/api/v1/comments/?task_id=1",
                "method": random.choice(["GET", "POST"]),
                "status_code": "500",
            },
            "request": {
                "url": "http://localhost:8001/api/v1/comments/?task_id=1",
                "method": "GET",
                "headers": {"Host": "localhost:8001"},
            },
            "exception": {
                "values": [
                    {
                        "type": "UndefinedTable",
                        "value": 'relation "comments" does not exist\nLINE 1: ...ments.content, comments.task_id FROM comments WHERE co...\n',
                        "module": "psycopg2.errors",
                        "mechanism": {"type": "logging", "handled": True},
                        "stacktrace": {
                            "frames": [
                                {
                                    "filename": "sqlalchemy/engine/default.py",
                                    "module": "sqlalchemy.engine.default",
                                    "function": "do_execute",
                                    "lineno": 922,
                                    "in_app": False,
                                },
                            ],
                        },
                    },
                    {
                        "type": "ProgrammingError",
                        "value": (
                            '(psycopg2.errors.UndefinedTable) relation "comments" does not exist\n'
                            "LINE 1: ...ments.content, comments.task_id FROM comments WHERE co...\n"
                            "                                                             ^\n\n"
                            "[SQL: SELECT comments.id AS comments_id, comments.content AS comments_content, "
                            "comments.task_id AS comments_task_id, comments.user_id AS comments_user_id, "
                            "comments.created_at AS comments_created_at, comments.updated_at AS comments_updated_at \n"
                            "FROM comments \nWHERE comments.task_id = %(task_id_1)s ORDER BY comments.created_at DESC\n"
                            " LIMIT %(param_1)s OFFSET %(param_2)s]\n"
                            "(Background on this error at: https://sqlalche.me/e/20/f405)"
                        ),
                        "module": "sqlalchemy.exc",
                        "mechanism": {"type": "logging", "handled": True},
                        "stacktrace": {
                            "frames": [
                                {
                                    "filename": "app/middleware.py",
                                    "absPath": "/app/app/middleware.py",
                                    "module": "app.middleware",
                                    "function": "dispatch",
                                    "lineno": 52,
                                    "in_app": True,
                                    "context_line": "            response = await call_next(request)",
                                },
                                {
                                    "filename": "app/routers/comments.py",
                                    "absPath": "/app/app/routers/comments.py",
                                    "module": "app.routers.comments",
                                    "function": "list_comments",
                                    "lineno": 23,
                                    "in_app": True,
                                    "context_line": "        .all()",
                                },
                            ],
                        },
                    },
                ],
            },
            "fingerprint": ["bug3-comments-table-missing"],
        }
        ok = send_event(event)
        if i == 0:
            print(f"  {'OK' if ok else 'FAIL'}")
        time.sleep(0.1)

    print(f"  Sent {count} events")


# ============================================================================
# Bug 6: AttributeError - 'State' object has no attribute 'user_role'
# (Auth reads request.state.user_role but middleware sets request.state.role)
# ============================================================================

def generate_bug6_errors(count=10):
    print(f"Bug 6: AttributeError (user_role) x{count}")

    endpoints = [
        ("POST", "/api/v1/tasks/", "create_task"),
        ("PATCH", "/api/v1/tasks/3", "update_task"),
        ("DELETE", "/api/v1/tasks/2", "delete_task"),
        ("POST", "/api/v1/comments/", "create_comment"),
    ]

    for i in range(count):
        method, path, func = random.choice(endpoints)
        user_id = random.choice([2, 3, 5])  # non-admin users
        event = {
            "logger": "app.middleware",
            "level": "error",
            "transaction": path,
            "user": {"id": str(user_id)},
            "tags": {
                "url": f"http://localhost:8001{path}",
                "method": method,
                "status_code": "500",
                "user_id": str(user_id),
            },
            "request": {
                "url": f"http://localhost:8001{path}",
                "method": method,
                "headers": {
                    "Host": "localhost:8001",
                    "X-User-Id": str(user_id),
                    "Content-Type": "application/json",
                },
            },
            "exception": {
                "values": [
                    {
                        "type": "AttributeError",
                        "value": "'State' object has no attribute 'user_role'",
                        "module": "builtins",
                        "mechanism": {"type": "logging", "handled": True},
                        "stacktrace": {
                            "frames": [
                                {
                                    "filename": "app/middleware.py",
                                    "absPath": "/app/app/middleware.py",
                                    "module": "app.middleware",
                                    "function": "dispatch",
                                    "lineno": 52,
                                    "in_app": True,
                                    "context_line": "            response = await call_next(request)",
                                },
                                {
                                    "filename": "fastapi/routing.py",
                                    "module": "fastapi.routing",
                                    "function": "run_endpoint_function",
                                    "lineno": 264,
                                    "in_app": False,
                                },
                                {
                                    "filename": "app/auth.py",
                                    "absPath": "/app/app/auth.py",
                                    "module": "app.auth",
                                    "function": "require_write_permission",
                                    "lineno": 35,
                                    "in_app": True,
                                    "context_line": "        role = request.state.user_role",
                                },
                            ],
                        },
                    },
                ],
            },
            "fingerprint": ["bug6-attributeerror-user-role"],
        }
        ok = send_event(event)
        if i == 0:
            print(f"  {'OK' if ok else 'FAIL'}")
        time.sleep(0.1)

    print(f"  Sent {count} events")


# ============================================================================
# Red Herring 1: OperationalError - QueuePool limit reached
# (Transient connection pool exhaustion under load)
# ============================================================================

def generate_red_herring_pool(count=5):
    print(f"Red Herring 1: OperationalError (pool) x{count}")

    for i in range(count):
        event = {
            "logger": "sqlalchemy.pool",
            "level": "error",
            "transaction": random.choice(["/api/v1/tasks/", "/api/v1/users/", "/api/v1/organizations/"]),
            "tags": {
                "status_code": "500",
                "pool_size": "5",
                "pool_overflow": "0",
            },
            "exception": {
                "values": [
                    {
                        "type": "TimeoutError",
                        "value": "QueuePool limit of size 5 overflow 0 reached, connection timed out, timeout 30.00",
                        "module": "sqlalchemy.exc",
                        "mechanism": {"type": "logging", "handled": True},
                        "stacktrace": {
                            "frames": [
                                {
                                    "filename": "sqlalchemy/pool/impl.py",
                                    "module": "sqlalchemy.pool.impl",
                                    "function": "_do_get",
                                    "lineno": 145,
                                    "in_app": False,
                                    "context_line": "            raise exc.TimeoutError(",
                                },
                                {
                                    "filename": "app/database.py",
                                    "absPath": "/app/app/database.py",
                                    "module": "app.database",
                                    "function": "get_db",
                                    "lineno": 19,
                                    "in_app": True,
                                    "context_line": "    db = SessionLocal()",
                                },
                            ],
                        },
                    },
                ],
            },
            "fingerprint": ["red-herring-pool-timeout"],
        }
        ok = send_event(event)
        if i == 0:
            print(f"  {'OK' if ok else 'FAIL'}")
        time.sleep(0.1)

    print(f"  Sent {count} events")


# ============================================================================
# Red Herring 2: DeprecationWarning - datetime.utcnow()
# ============================================================================

def generate_red_herring_deprecation(count=12):
    print(f"Red Herring 2: DeprecationWarning (utcnow) x{count}")

    locations = [
        ("app/models.py", "Organization", 16),
        ("app/models.py", "User", 35),
        ("app/models.py", "Task", 54),
    ]

    for i in range(count):
        filename, cls, lineno = random.choice(locations)
        event = {
            "logger": "py.warnings",
            "level": "warning",
            "transaction": random.choice(["/api/v1/tasks/", "/api/v1/users/", "/api/v1/organizations/"]),
            "message": f"DeprecationWarning: datetime.utcnow() is deprecated and scheduled for removal in a future version. Use timezone-aware objects to represent datetimes in UTC; e.g. by calling .now(datetime.timezone.utc)",
            "tags": {
                "source": filename,
                "class": cls,
            },
            "logentry": {
                "message": "DeprecationWarning: datetime.utcnow() is deprecated and scheduled for removal in a future version.",
                "params": [],
            },
            "fingerprint": ["red-herring-utcnow-deprecation"],
        }
        ok = send_event(event)
        if i == 0:
            print(f"  {'OK' if ok else 'FAIL'}")
        time.sleep(0.05)

    print(f"  Sent {count} events")


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Generating Sentry errors for task-tracker-v2")
    print(f"DSN: {SENTRY_DSN}")
    print(f"Store URL: {STORE_URL}")
    print("=" * 60)

    generate_bug1_errors(30)
    time.sleep(1)

    generate_bug2_errors(15)
    time.sleep(1)

    generate_bug3_errors(8)
    time.sleep(1)

    generate_bug6_errors(10)
    time.sleep(1)

    generate_red_herring_pool(5)
    time.sleep(1)

    generate_red_herring_deprecation(12)

    print("\n" + "=" * 60)
    print("Done! Total: 80 events across 6 issue groups")
    print("Wait ~30s for Sentry to process, then export.")
    print("=" * 60)
