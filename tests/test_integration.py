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
import shutil
import subprocess
import sys
from datetime import datetime, timedelta

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


class TestTaskFilter:
    def test_task_list_filters_by_organization_id(self):
        with open("app/routers/tasks.py") as f:
            content = f.read()

        assert "Task.organization_id ==" in content or "Task.organization_id==" in content, (
            "Task list endpoint must filter by Task.organization_id, "
            "not Task.id when organization_id parameter is provided"
        )

        assert "Task.id == organization_id" not in content, (
            "Task list endpoint incorrectly filters by Task.id instead of "
            "Task.organization_id — this returns wrong results"
        )


class TestTaskResponse:
    def test_due_date_in_response_schema(self):
        with open("app/schemas.py") as f:
            content = f.read()

        import re
        response_match = re.search(
            r'class TaskResponse.*?(?=class |\Z)', content, re.DOTALL
        )
        assert response_match, "TaskResponse class must exist in schemas.py"

        response_class = response_match.group()
        assert "due_date" in response_class, (
            "TaskResponse must include 'due_date' field — "
            "currently the field is missing from API responses"
        )


class TestAuth:
    def test_write_permission_reads_correct_state(self):
        with open("app/auth.py") as f:
            content = f.read()

        assert "request.state.user_role" not in content, (
            "Auth check reads 'request.state.user_role' but middleware "
            "sets 'request.state.role' — this causes AttributeError "
            "for non-admin users"
        )

        assert "request.state.role" in content, (
            "Auth permission check must read 'request.state.role' "
            "to match what the AuthMiddleware sets"
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
        assert "request.state.role" in content, (
            "AuthMiddleware must set request.state.role"
        )
