"""Controlled web surface for the Quarantine Browser Clerk demo."""
from __future__ import annotations

import ipaddress
import json
import os
import re
import secrets
import sqlite3
import uuid
from threading import Lock
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from clerk.allowlist import Allowlist, host_of
from clerk.docker_sandbox import DockerSandbox, SandboxExecutionError

DB_PATH = Path(os.environ.get(
    "QBC_DB_PATH", "/tmp/qbc-tasks.sqlite3"))
MAX_ACTIVE_TASKS = max(1, int(os.environ.get("QBC_MAX_ACTIVE_TASKS", "1")))
INDEX_PATH = Path(__file__).parent / "static" / "index.html"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskRequest(BaseModel):
    url: str
    allowed_domains: list[str] = Field(default_factory=list)
    fields: dict[str, str]
    timeout_s: int = Field(default=120, ge=15, le=180)

    @field_validator("url")
    @classmethod
    def https_only(cls, value: str) -> str:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https" or not host:
            raise ValueError("Only absolute HTTPS URLs are accepted")
        if parsed.username or parsed.password:
            raise ValueError("URL user-info is not allowed")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError("Private, loopback, and reserved IPs are blocked")
        return value

    @field_validator("fields")
    @classmethod
    def safe_fields(cls, value: dict[str, str]) -> dict[str, str]:
        if not value or len(value) > 8:
            raise ValueError("Provide between 1 and 8 extraction fields")
        for name, selector in value.items():
            if (not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,31}", name)
                    or not selector.strip() or len(selector) > 256):
                raise ValueError("Invalid field name or CSS selector")
        return value

    @model_validator(mode="after")
    def scope_target(self):
        host = host_of(self.url)
        normalized = []
        for domain in self.allowed_domains:
            item = domain.strip().lower()
            if (not re.fullmatch(r"\.?[a-z0-9.-]{1,253}", item)
                    or ".." in item or item.startswith("-")
                    or item.endswith("-")):
                raise ValueError("Invalid allowlist domain")
            normalized.append(item)
        if not normalized:
            normalized = [host]
        if len(normalized) > 16:
            raise ValueError("At most 16 allowlist domains are accepted")
        if not Allowlist(normalized).allows(self.url):
            raise ValueError("The target host is outside the task allowlist")
        self.allowed_domains = sorted(set(normalized))
        return self

    def to_task(self, task_id: str) -> dict:
        return {
            "id": task_id,
            "url": self.url,
            "allowed_domains": self.allowed_domains,
            "timeout_s": self.timeout_s,
            "steps": [
                {"action": "goto", "url": self.url},
                {"action": "extract", "fields": self.fields},
            ],
        }


class TaskStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.session() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    task_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT
                )
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    @contextmanager
    def session(self):
        db = self.connect()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def create(self, task_id: str, task: dict) -> None:
        stamp = now()
        with self.session() as db:
            db.execute(
                "INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?)",
                (task_id, "queued", stamp, stamp,
                 json.dumps(task), None, None))

    def update(self, task_id: str, status: str,
               result: dict | None = None, error: str | None = None):
        with self.connect() as db:
            db.execute(
                "UPDATE tasks SET status=?, updated_at=?, result_json=?, error=? WHERE id=?",
                (status, now(), json.dumps(result) if result is not None else None,
                 error, task_id))

    def get(self, task_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row else None

    def list(self, limit: int = 20) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT id,status,created_at,updated_at FROM tasks "
                "ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def active_count(self) -> int:
        with self.connect() as db:
            row = db.execute(
                "SELECT COUNT(*) AS n FROM tasks WHERE status IN ('queued','running')"
            ).fetchone()
        return int(row["n"])


STORE = TaskStore(DB_PATH)
TASK_CREATION_LOCK = Lock()
app = FastAPI(title="Quarantine Browser Clerk", version="0.1.0")


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'")
    return response


def require_demo_token(x_qbc_demo_token: str = Header(default="")):
    expected = os.environ.get("QBC_DEMO_TOKEN", "")
    if len(expected) < 32:
        raise HTTPException(
            status_code=503,
            detail="Demo API requires a configured QBC_DEMO_TOKEN of at least 32 characters")
    if not secrets.compare_digest(x_qbc_demo_token, expected):
        raise HTTPException(status_code=401, detail="Invalid demo token")


def execute_task(task_id: str, task: dict):
    STORE.update(task_id, "running")
    try:
        result = DockerSandbox().run(task)
        STORE.update(task_id, result.get("status", "complete"),
                     result=result)
    except Exception as exc:
        STORE.update(task_id, "failed",
                     error=f"{type(exc).__name__}: {str(exc)[:500]}")


@app.get("/", response_class=HTMLResponse)
def home():
    return INDEX_PATH.read_text()


@app.get("/healthz")
def health():
    return {"ok": True, "sandbox": "docker-required"}


@app.get("/api/tasks")
def list_tasks(_auth: None = Depends(require_demo_token)):
    return {"tasks": STORE.list()}


@app.post("/api/tasks", status_code=202)
def create_task(payload: TaskRequest, background: BackgroundTasks,
                _auth: None = Depends(require_demo_token)):
    with TASK_CREATION_LOCK:
        if STORE.active_count() >= MAX_ACTIVE_TASKS:
            raise HTTPException(status_code=429, detail="Task capacity reached")
        task_id = uuid.uuid4().hex
        task = payload.to_task(task_id)
        STORE.create(task_id, task)
    background.add_task(execute_task, task_id, task)
    return {"task_id": task_id, "status": "queued"}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str,
             _auth: None = Depends(require_demo_token)):
    row = STORE.get(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    result = json.loads(row["result_json"]) if row["result_json"] else None
    return {
        "task_id": row["id"], "status": row["status"],
        "created_at": row["created_at"], "updated_at": row["updated_at"],
        "result": result, "error": row["error"],
    }


@app.get("/api/tasks/{task_id}/receipts")
def get_receipts(task_id: str,
                 _auth: None = Depends(require_demo_token)):
    row = STORE.get(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    result = json.loads(row["result_json"]) if row["result_json"] else {}
    return {"task_id": task_id, "receipts": result.get("receipts", [])}
