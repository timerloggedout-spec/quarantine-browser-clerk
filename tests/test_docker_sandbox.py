import json
import subprocess
from pathlib import Path

from clerk.docker_sandbox import DockerSandbox


def test_docker_sandbox_uses_internal_network_and_cleans_up(
        tmp_path, monkeypatch):
    calls = []
    task_payloads = []

    def fake_which(_name):
        return "/usr/bin/docker"

    def fake_run(args, **kwargs):
        calls.append(list(args))
        if "clerk.cli" in args:
            mount = next(item for item in args
                         if item.startswith("type=bind,src=")
                         and "/task/task.json" in item)
            source = mount.split("src=", 1)[1].split(",dst=", 1)[0]
            task_payloads.append(json.loads(Path(source).read_text()))
            return subprocess.CompletedProcess(
                args, 0,
                stdout=json.dumps({
                    "task_id": "safe-task", "status": "complete",
                    "extracted": {"title": "Example Domain"},
                    "receipts": [], "receipt_chain_valid": True,
                }), stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")

    monkeypatch.setattr("clerk.docker_sandbox.shutil.which", fake_which)
    monkeypatch.setattr("clerk.docker_sandbox.subprocess.run", fake_run)

    result = DockerSandbox(
        image="qbc-test:latest", work_root=tmp_path).run({
            "id": "safe-task", "url": "https://example.com/",
            "allowed_domains": ["example.com"],
            "steps": [{"action": "goto",
                       "url": "https://example.com/"}],
        })

    assert result["status"] == "complete"
    commands = [" ".join(c) for c in calls]
    assert any("network create --internal" in c for c in commands)
    assert any("--read-only" in c and "--cap-drop ALL" in c
               and "no-new-privileges" in c for c in commands)
    assert any("network connect --alias qbc-proxy" in c
               for c in commands)
    assert any("network rm" in c for c in commands)
    assert any("rm -f" in c for c in commands)
    assert task_payloads[0]["proxy_server"] == "http://qbc-proxy:3128"
    assert list(tmp_path.iterdir()) == []
