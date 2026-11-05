"""Run a task in a disposable, egress-restricted Docker sandbox.

The task container is attached only to an internal Docker network. A small
proxy sidecar is attached to that network and the external bridge; it allows
only HTTPS/443 CONNECT to task-allowlisted hosts resolving to public IPs.
Neither the browser container nor its filesystem is reused across tasks.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from .allowlist import host_of


class SandboxExecutionError(RuntimeError):
    pass


class DockerSandbox:
    def __init__(self, image: str | None = None,
                 work_root: str | Path | None = None,
                 docker_bin: str | None = None):
        self.image = image or os.environ.get(
            "QBC_SANDBOX_IMAGE", "qbc-sandbox:latest")
        self.work_root = Path(work_root or os.environ.get(
            "QBC_WORK_ROOT", "/var/lib/qbc/sandboxes"))
        self.docker = docker_bin or os.environ.get("DOCKER_BIN", "docker")

    def _call(self, args: list[str], timeout: int = 30,
              check: bool = True) -> subprocess.CompletedProcess:
        try:
            result = subprocess.run(
                [self.docker, *args], capture_output=True,
                text=True, timeout=timeout, check=False)
        except FileNotFoundError as exc:
            raise SandboxExecutionError(
                "Docker CLI is unavailable on the Vultr app host") from exc
        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout or "")[-1200:]
            raise SandboxExecutionError(
                f"Docker command failed ({result.returncode}): {detail}")
        return result

    def run(self, task: dict) -> dict:
        if not shutil.which(self.docker):
            raise SandboxExecutionError("Docker CLI is not installed")
        self.work_root.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex[:12]
        network = f"qbc-task-{token}"
        proxy_name = f"qbc-proxy-{token}"
        browser_name = f"qbc-browser-{token}"
        root = Path(tempfile.mkdtemp(
            prefix=f"qbc-{token}-", dir=self.work_root))
        task_dir = root / "task"
        out_dir = root / "out"
        task_dir.mkdir()
        out_dir.mkdir()
        os.chmod(root, 0o755)
        os.chmod(task_dir, 0o755)
        os.chmod(out_dir, 0o700)

        uid, gid = os.getuid(), os.getgid()
        if uid == 0:
            uid, gid = 10001, 10001
            os.chown(out_dir, uid, gid)

        task_path = task_dir / "task.json"
        task_for_container = dict(task)
        task_for_container["proxy_server"] = "http://qbc-proxy:3128"
        task_path.write_text(json.dumps(task_for_container))
        os.chmod(task_path, 0o400)
        if os.geteuid() == 0:
            os.chown(task_path, uid, gid)

        domains = list(task.get("allowed_domains") or [])
        start_host = host_of(task.get("url", ""))
        if start_host and start_host not in domains:
            domains.append(start_host)
        if not domains:
            raise SandboxExecutionError("task allowlist is empty")

        try:
            self._call(["network", "create", "--internal", network])
            self._call([
                "run", "--detach", "--name", proxy_name,
                "--network", "bridge", "--read-only",
                "--tmpfs", "/tmp:rw,nosuid,nodev,size=16m",
                "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges",
                "--pids-limit", "64", "--memory", "128m",
                "--cpus", "0.25", "--user", "10001:10001",
                "--env", "QBC_ALLOWED_DOMAINS=" + json.dumps(domains),
                self.image, "python", "-m", "clerk.egress_proxy"])
            self._call([
                "network", "connect", "--alias", "qbc-proxy",
                network, proxy_name])

            # Wait for the proxy listener before starting Chromium.
            ready = False
            for _ in range(40):
                probe = self._call([
                    "exec", proxy_name, "python", "-c",
                    "import socket; s=socket.create_connection(('127.0.0.1',3128),1); s.close()"],
                    timeout=3, check=False)
                if probe.returncode == 0:
                    ready = True
                    break
                time.sleep(0.25)
            if not ready:
                raise SandboxExecutionError(
                    "egress proxy did not become ready")

            result = self._call([
                "run", "--rm", "--name", browser_name,
                "--network", network, "--read-only",
                "--tmpfs", "/tmp:rw,nosuid,nodev,size=1g",
                "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges",
                "--pids-limit", "256", "--memory", "2g",
                "--cpus", "2", "--shm-size", "1g",
                "--user", f"{uid}:{gid}",
                "--env", "HOME=/tmp",
                "--env", "PLAYWRIGHT_BROWSERS_PATH=/ms-playwright",
                "--mount", f"type=bind,src={task_path},dst=/task/task.json,readonly",
                "--mount", f"type=bind,src={out_dir},dst=/out",
                self.image, "python", "-m", "clerk.cli", "run",
                "/task/task.json", "--workdir", "/out"],
                timeout=int(task.get("timeout_s", 120)) + 20,
                check=False)
            if result.returncode not in (0, 2):
                detail = (result.stderr or result.stdout or "")[-1200:]
                raise SandboxExecutionError(
                    f"task container failed ({result.returncode}): {detail}")
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError as exc:
                raise SandboxExecutionError(
                    "task container returned invalid result JSON") from exc
        except subprocess.TimeoutExpired as exc:
            raise SandboxExecutionError(
                "sandbox task exceeded its execution timeout") from exc
        finally:
            self._call(["rm", "-f", browser_name], timeout=15, check=False)
            self._call(["rm", "-f", proxy_name], timeout=15, check=False)
            self._call(["network", "rm", network], timeout=15, check=False)
            shutil.rmtree(root, ignore_errors=True)
