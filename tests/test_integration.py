"""
Integration tests for the Task Tracker API.

These tests verify that the complete application works correctly:
- Database migrations run successfully against PostgreSQL
- All API endpoints function properly
- Data integrity is maintained across operations

Requirements:
- PostgreSQL running and accessible
- DATABASE_URL environment variable set
"""
import os
import signal
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta

import httpx
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_docker_compose_api_env():
    import yaml
    with open("docker-compose.yml") as f:
        compose = yaml.safe_load(f)
    api_service = compose.get("services", {}).get("api", {})
    raw_env = api_service.get("environment", {})
    if isinstance(raw_env, list):
        env = {}
        for item in raw_env:
            if "=" in str(item):
                k, v = str(item).split("=", 1)
                env[k] = v
        return env
    if isinstance(raw_env, dict):
        return {k: str(v) for k, v in raw_env.items() if v is not None}
    return {}


def _find_postgres_url(env_dict):
    for key, value in env_dict.items():
        if "postgresql://" in str(value):
            return key, str(value)
    return None, None


def _find_alembic_bin():
    alembic_bin = shutil.which("alembic")
    if alembic_bin:
        return alembic_bin
    candidate = os.path.join(os.path.dirname(sys.executable), "alembic")
    if os.path.isfile(candidate):
        return candidate
    return None


def _run_alembic(alembic_bin, args, env):
    return subprocess.run(
        [alembic_bin] + args,
        capture_output=True,
        text=True,
        env=env,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def api_env():
    return _get_docker_compose_api_env()


@pytest.fixture(scope="session")
def db_url(api_env):
    _, url = _find_postgres_url(api_env)
    assert url, f"No postgresql:// URL in docker-compose env: {api_env}"
    return url


@pytest.fixture(scope="session")
def run_env(api_env):
    env = {**os.environ}
    env.update(api_env)
    return env


# ---------------------------------------------------------------------------
# Test 1: Alembic migrations target PostgreSQL and complete successfully
# ---------------------------------------------------------------------------

class TestMigrations:
    def test_alembic_generates_postgres_ddl(self, run_env):
        alembic_bin = _find_alembic_bin()
        assert alembic_bin, "alembic binary not found"

        result = _run_alembic(alembic_bin, ["upgrade", "head", "--sql"], run_env)
        output = result.stdout

        assert "CREATE TABLE" in output, (
            f"Alembic --sql produced no DDL.\n"
            f"stderr: {result.stderr[:500]}"
        )
        assert "SERIAL" in output, (
            f"Alembic generated SQLite DDL instead of PostgreSQL.\n"
            f"DDL preview:\n{output[:400]}"
        )

    def test_migrations_create_all_tables(self, run_env):
        alembic_bin = _find_alembic_bin()
        assert alembic_bin, "alembic binary not found"

        result = _run_alembic(alembic_bin, ["upgrade", "head", "--sql"], run_env)
        output = result.stdout

        assert "CREATE TABLE organizations" in output, "Migration must create organizations table"
        assert "CREATE TABLE users" in output, "Migration must create users table"
        assert "CREATE TABLE tasks" in output, "Migration must create tasks table"
        assert "CREATE TABLE comments" in output, "Migration must create comments table"
        assert "CREATE TABLE audit_log" in output, "Migration must create audit_log table"

    def test_due_date_column_valid(self, run_env):
        alembic_bin = _find_alembic_bin()
        assert alembic_bin

        result = _run_alembic(alembic_bin, ["upgrade", "head", "--sql"], run_env)
        output = result.stdout

        assert "due_date" in output, "Migration must add due_date column"

        lines = output.split("\n")
        due_date_lines = [l for l in lines if "due_date" in l.lower()]
        for line in due_date_lines:
            assert "'not_set'" not in line, (
                f"due_date column must not have 'not_set' as default value.\n"
                f"Found: {line.strip()}"
            )

    def test_comments_index_valid(self, run_env):
        alembic_bin = _find_alembic_bin()
        assert alembic_bin

        result = _run_alembic(alembic_bin, ["upgrade", "head", "--sql"], run_env)
        output = result.stdout

        assert "CREATE TABLE comments" in output, "comments table must be created"
        assert "taks_id" not in output, (
            "Migration has typo 'taks_id' — should be 'task_id'"
        )


# ---------------------------------------------------------------------------
# Test 2: Application code correctness
# ---------------------------------------------------------------------------

class TestAppConfig:
    def test_app_config_resolves_to_postgres(self, run_env):
        filtered_env = {**run_env}
        for k, v in run_env.items():
            if str(v).startswith("${"):
                del filtered_env[k]

        script = (
            "import os\n"
            "with open('app/config.py') as f:\n"
            "    source = f.read()\n"
            "ns = {'os': os, '__builtins__': __builtins__}\n"
            "exec(compile(source, 'app/config.py', 'exec'), ns)\n"
            "for name, val in ns.items():\n"
            "    if isinstance(val, str) and ('postgresql://' in val or 'sqlite://' in val):\n"
            "        print(f'{name}={val}')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, env=filtered_env,
        )
        assert "postgresql://" in result.stdout, (
            f"app/config.py resolves to SQLite instead of PostgreSQL.\n"
            f"Output: {result.stdout.strip()}"
        )


# ---------------------------------------------------------------------------
# Behavioral test fixtures — starts the actual app against a test database
# ---------------------------------------------------------------------------

def _find_system_python():
    for p in ["/usr/bin/python3", "/usr/bin/python"]:
        if os.path.isfile(p):
            return p
    return sys.executable


def _resolve_pg_url(url):
    """Replace docker-compose service hostnames with localhost for local testing."""
    # docker-compose.yml uses 'db' as hostname; inside the grading container
    # Postgres runs locally on localhost:5432
    import re
    return re.sub(r'@[^:/@]+:', '@localhost:', url)


@pytest.fixture(scope="session")
def app_server(run_env):
    """Start the FastAPI app against a fresh test database, yield base URL."""
    test_db = "tasktracker_test"
    port = 9876
    base_url = f"http://127.0.0.1:{port}"
    system_python = _find_system_python()

    api_env = _get_docker_compose_api_env()
    _, pg_url = _find_postgres_url(api_env)
    assert pg_url, "No postgresql:// URL found in docker-compose.yml"
    pg_url = _resolve_pg_url(pg_url)

    test_db_url = pg_url.rsplit("/", 1)[0] + f"/{test_db}"

    import psycopg2

    conn = psycopg2.connect(pg_url)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {test_db}")
    cur.execute(f"CREATE DATABASE {test_db} OWNER tasktracker")
    cur.close()
    conn.close()

    alembic_bin = _find_alembic_bin()
    assert alembic_bin, "alembic not found"

    mig_env = {**run_env}
    for key in list(mig_env.keys()):
        if "postgresql://" in str(mig_env.get(key, "")):
            mig_env[key] = test_db_url
    mig_env["DATABASE_URL"] = test_db_url

    result = subprocess.run(
        [alembic_bin, "upgrade", "head"],
        capture_output=True, text=True, env=mig_env, cwd=os.getcwd(),
    )
    assert result.returncode == 0, (
        f"alembic upgrade head failed (exit {result.returncode}):\n"
        f"stdout: {result.stdout[-500:]}\n"
        f"stderr: {result.stderr[-500:]}"
    )

    app_env = {**os.environ}
    app_env.update(mig_env)
    # Strip shell variable expansions (e.g. ${SENTRY_DSN:-}) that YAML
    # parses as literal strings — they'd crash Sentry SDK init etc.
    for k in list(app_env.keys()):
        v = str(app_env.get(k, ""))
        if v.startswith("${") or v == "":
            del app_env[k]

    proc = subprocess.Popen(
        [system_python, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=os.getcwd(),
        env=app_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    ready = False
    for _ in range(20):
        try:
            resp = httpx.get(f"{base_url}/health", timeout=2)
            if resp.status_code == 200:
                ready = True
                break
        except Exception:
            pass
        time.sleep(0.5)

    if not ready:
        proc.kill()
        proc.wait()
        stderr_out = ""
        try:
            stderr_out = proc.stderr.read().decode(errors="replace")[-1000:]
        except Exception:
            pass
        pytest.fail(
            f"App did not start within 10s on port {port}.\n"
            f"stderr: {stderr_out}"
        )

    yield base_url

    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()

    try:
        conn = psycopg2.connect(pg_url)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(f"DROP DATABASE IF EXISTS {test_db}")
        cur.close()
        conn.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Behavioral tests (Bugs 4, 5, 6) — test actual API behavior via HTTP
# ---------------------------------------------------------------------------

class TestTaskFilterBehavior:
    def test_task_list_filters_by_organization_id(self, app_server):
        base = app_server

        org_a = httpx.post(f"{base}/api/v1/organizations/", json={
            "name": "Org Alpha", "slug": "org-alpha-test"
        }, timeout=10).json()

        org_b = httpx.post(f"{base}/api/v1/organizations/", json={
            "name": "Org Beta", "slug": "org-beta-test"
        }, timeout=10).json()

        for title in ["Alpha Task 1", "Alpha Task 2"]:
            resp = httpx.post(f"{base}/api/v1/tasks/", json={
                "title": title, "organization_id": org_a["id"]
            }, timeout=10)
            assert resp.status_code == 201, f"Failed to create task: {resp.text}"

        resp = httpx.post(f"{base}/api/v1/tasks/", json={
            "title": "Beta Task 1", "organization_id": org_b["id"]
        }, timeout=10)
        assert resp.status_code == 201, f"Failed to create task: {resp.text}"

        resp = httpx.get(
            f"{base}/api/v1/tasks/",
            params={"organization_id": org_a["id"]},
            timeout=10,
        )
        assert resp.status_code == 200
        tasks = resp.json()

        org_a_tasks = [t for t in tasks if t["organization_id"] == org_a["id"]]
        org_b_tasks = [t for t in tasks if t["organization_id"] == org_b["id"]]

        assert len(org_a_tasks) >= 2, (
            f"Expected at least 2 tasks for org {org_a['id']}, got {len(org_a_tasks)}. "
            f"The organization_id filter may be broken."
        )
        assert len(org_b_tasks) == 0, (
            f"Filtering by organization_id={org_a['id']} returned tasks from org "
            f"{org_b['id']}. The filter is not working correctly."
        )


class TestTaskResponseBehavior:
    def test_due_date_in_api_response(self, app_server):
        base = app_server

        org_resp = httpx.post(f"{base}/api/v1/organizations/", json={
            "name": "Due Date Test Org", "slug": "duedate-test-org"
        }, timeout=10)
        org = org_resp.json()
        org_id = org.get("id", 1)

        create_resp = httpx.post(f"{base}/api/v1/tasks/", json={
            "title": "Task with due date",
            "organization_id": org_id,
            "due_date": "2026-06-15T00:00:00",
        }, timeout=10)
        assert create_resp.status_code == 201, (
            f"Failed to create task with due_date: {create_resp.text}"
        )
        task = create_resp.json()
        task_id = task["id"]

        get_resp = httpx.get(f"{base}/api/v1/tasks/{task_id}", timeout=10)
        assert get_resp.status_code == 200
        task_data = get_resp.json()

        assert "due_date" in task_data, (
            f"API response for task {task_id} is missing 'due_date' field. "
            f"Response keys: {list(task_data.keys())}. "
            f"The TaskResponse schema likely needs to include due_date."
        )
        assert task_data["due_date"] is not None, (
            f"due_date was set to '2026-06-15T00:00:00' but API returned None."
        )


class TestAuthBehavior:
    def test_non_admin_can_create_tasks(self, app_server):
        base = app_server

        org_resp = httpx.post(f"{base}/api/v1/organizations/", json={
            "name": "Auth Test Org", "slug": "auth-test-org"
        }, timeout=10)
        org = org_resp.json()
        org_id = org.get("id", 1)

        user_resp = httpx.post(f"{base}/api/v1/users/", json={
            "username": "member_test_user",
            "email": "member@test.com",
            "full_name": "Test Member",
            "role": "member",
            "organization_id": org_id,
        }, timeout=10)
        assert user_resp.status_code == 201, (
            f"Failed to create test user: {user_resp.text}"
        )
        user = user_resp.json()

        task_resp = httpx.post(
            f"{base}/api/v1/tasks/",
            json={"title": "Member-created task", "organization_id": org_id},
            headers={"X-User-Id": str(user["id"])},
            timeout=10,
        )

        assert task_resp.status_code != 500, (
            f"Creating a task as a non-admin user returned 500. "
            f"This likely means the permission check has an AttributeError. "
            f"Response: {task_resp.text}"
        )
        assert task_resp.status_code != 403, (
            f"Creating a task as a 'member' role user returned 403 Forbidden. "
            f"Members should have write permissions. "
            f"Response: {task_resp.text}"
        )
        assert task_resp.status_code in (200, 201), (
            f"Expected 200 or 201 for task creation, got {task_resp.status_code}. "
            f"Response: {task_resp.text}"
        )


# ---------------------------------------------------------------------------
# Guard tests
# ---------------------------------------------------------------------------

class TestGuards:
    def test_priority_field_intact(self):
        with open("app/models.py") as f:
            content = f.read()
        assert "priority" in content, "Task model must have a 'priority' field"

        migration_dir = "alembic/versions"
        assert os.path.isdir(migration_dir)
        files = os.listdir(migration_dir)
        assert any("priority" in f.lower() for f in files), (
            "A migration for the priority column must exist"
        )

    def test_due_date_field_intact(self):
        with open("app/models.py") as f:
            content = f.read()
        assert "due_date" in content, "Task model must have a 'due_date' field"

    def test_comments_model_intact(self):
        with open("app/models.py") as f:
            content = f.read()
        assert "class Comment" in content, "Comment model must exist"
        assert "comments" in content, "comments table must be defined"

    def test_auth_middleware_exists(self):
        with open("app/middleware.py") as f:
            content = f.read()
        assert "class AuthMiddleware" in content, "AuthMiddleware must exist"
        assert "request.state." in content, (
            "AuthMiddleware must set a role attribute on request.state"
        )
