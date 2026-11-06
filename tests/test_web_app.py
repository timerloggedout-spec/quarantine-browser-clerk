import pytest
from pydantic import ValidationError

from web.app import TaskRequest


def test_web_task_defaults_to_exact_target_host():
    task = TaskRequest(
        url="https://example.com/",
        fields={"title": "title"})
    assert task.allowed_domains == ["example.com"]
    assert task.to_task("t1")["steps"][0]["action"] == "goto"


def test_web_task_rejects_http_and_private_ip():
    with pytest.raises(ValidationError):
        TaskRequest(url="http://example.com/",
                    fields={"title": "title"})
    with pytest.raises(ValidationError):
        TaskRequest(url="https://127.0.0.1/",
                    fields={"title": "title"})


def test_web_task_rejects_target_outside_allowlist():
    with pytest.raises(ValidationError):
        TaskRequest(url="https://example.com/",
                    allowed_domains=["evil.example"],
                    fields={"title": "title"})


def test_web_task_limits_extraction_surface():
    with pytest.raises(ValidationError):
        TaskRequest(url="https://example.com/",
                    fields={})
    with pytest.raises(ValidationError):
        TaskRequest(url="https://example.com/",
                    fields={"bad name": "title"})


def test_task_store_marks_interrupted_runs_after_restart(tmp_path):
    from web.app import TaskStore

    store = TaskStore(tmp_path / "tasks.sqlite3")
    task = {"id": "t-restart", "url": "https://example.com/"}
    store.create("t-restart", task)
    store.update("t-restart", "running")
    store.mark_interrupted()
    row = store.get("t-restart")
    assert row["status"] == "failed"
    assert row["error"] == "interrupted by service restart"
