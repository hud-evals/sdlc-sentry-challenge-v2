#!/usr/bin/env python3
"""Seed the database with sample data for development."""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Organization, User, Task

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)


def seed():
    db = Session()

    org1 = Organization(name="Acme Corp", slug="acme-corp", description="Main engineering team")
    org2 = Organization(name="Globex Inc", slug="globex-inc", description="Product division")
    db.add_all([org1, org2])
    db.flush()

    users = [
        User(username="alice", email="alice@acme.com", full_name="Alice Chen", role="admin", organization_id=org1.id),
        User(username="bob", email="bob@acme.com", full_name="Bob Smith", role="member", organization_id=org1.id),
        User(username="carol", email="carol@acme.com", full_name="Carol Davis", role="member", organization_id=org1.id),
        User(username="dave", email="dave@globex.com", full_name="Dave Wilson", role="admin", organization_id=org2.id),
        User(username="eve", email="eve@globex.com", full_name="Eve Johnson", role="member", organization_id=org2.id),
    ]
    db.add_all(users)
    db.flush()

    now = datetime.utcnow()
    tasks = [
        Task(title="Set up CI/CD pipeline", description="Configure GitHub Actions", status="done", priority="high", organization_id=org1.id, assigned_to=users[0].id, due_date=now - timedelta(days=5)),
        Task(title="Fix login bug", description="Users unable to log in with SSO", status="in_progress", priority="critical", organization_id=org1.id, assigned_to=users[1].id, due_date=now + timedelta(days=2)),
        Task(title="Update API docs", description="Swagger docs are outdated", status="open", priority="low", organization_id=org1.id, assigned_to=users[2].id, due_date=now + timedelta(days=14)),
        Task(title="Database optimization", description="Slow queries on task list", status="open", priority="medium", organization_id=org1.id, assigned_to=users[0].id, due_date=now + timedelta(days=7)),
        Task(title="Design new dashboard", description="Mockups for v2 dashboard", status="in_progress", priority="high", organization_id=org2.id, assigned_to=users[3].id, due_date=now + timedelta(days=10)),
        Task(title="Security audit", description="Annual security review", status="open", priority="critical", organization_id=org2.id, assigned_to=users[4].id, due_date=now + timedelta(days=30)),
        Task(title="Migrate to PostgreSQL 16", description="Upgrade database version", status="open", priority="medium", organization_id=org2.id, assigned_to=users[3].id),
        Task(title="Write integration tests", description="Cover all API endpoints", status="open", priority="high", organization_id=org1.id, assigned_to=users[1].id, due_date=now + timedelta(days=21)),
    ]
    db.add_all(tasks)
    db.commit()
    print(f"Seeded {len([org1, org2])} orgs, {len(users)} users, {len(tasks)} tasks")
    db.close()


if __name__ == "__main__":
    seed()
