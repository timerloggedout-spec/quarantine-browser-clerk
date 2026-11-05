import json
import subprocess
from pathlib import Path

from clerk.docker_sandbox import DockerSandbox


def test_docker_sandbox_uses_uid_firewalled_proxy_namespace_and_cleans_up(
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
    assert any("--read-only" in c and "--cap-drop ALL" in c
               and "no-new-privileges" in c for c in commands)
    assert any("rm -f" in c for c in commands)
    assert any("clerk.egress_proxy" in c and "--cap-add NET_ADMIN" in c
               and "--cap-add SETUID" in c and "--user 0:0" in c
               for c in commands)
    assert any("--network container:qbc-proxy-" in c
               for c in commands)
    assert task_payloads[0]["proxy_server"] == "http://127.0.0.1:3128"
    assert list(tmp_path.iterdir()) == []


def test_cleanup_orphans_is_scoped_to_qbc_labels(monkeypatch, tmp_path):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(list(args))
        if args[1:3] == ["ps", "-aq"]:
            return subprocess.CompletedProcess(
                args, 0, stdout="browser-id\nproxy-id\n", stderr="")
        if args[1:4] == ["network", "ls", "-q"]:
            return subprocess.CompletedProcess(
                args, 0, stdout="network-id\n", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr("clerk.docker_sandbox.shutil.which",
                        lambda _name: "/usr/bin/docker")
    monkeypatch.setattr("clerk.docker_sandbox.subprocess.run", fake_run)

    DockerSandbox(work_root=tmp_path).cleanup_orphans()

    joined = [" ".join(call) for call in calls]
    assert any("label=com.timerloggedout-spec.qbc=true" in call
               for call in joined)
    assert any("rm -f browser-id" in call for call in joined)
    assert any("rm -f proxy-id" in call for call in joined)
    assert any("network rm network-id" in call for call in joined)
    stale = tmp_path / "qbc-stale-task"
    stale.mkdir()
    (stale / "partial.json").write_text("{}")
    unrelated = tmp_path / "other-service"
    unrelated.mkdir()
    DockerSandbox(work_root=tmp_path).cleanup_orphans()
    assert not stale.exists()
    assert unrelated.exists()

