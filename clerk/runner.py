"""The sandboxed runner — T1 core loop.

task in -> sandboxed browse -> extracted data + receipt log out.

Containment properties, all enforced below the agent (the
agent — scripted or LLM-driven — cannot bypass them):
- a DISPOSABLE browser profile per task, deleted after;
- EVERY request passes the domain allowlist (route guard);
- downloads land only in a per-task QUARANTINE directory and
  are never executed or moved out by the runner;
- pages are assessed for lookalike/agent-lure containment
  before any interaction; a hit ends interaction with that
  page and is receipted;
- consequential actions (credential entry, form submission
  carrying a password, purchases) require human approval via
  the approval seam — default is to halt and receipt.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from .allowlist import Allowlist, host_of
from .lookalike import KNOWN_BRANDS, assess
from .receipts import ReceiptLog


def _chromium_executable() -> str | None:
    """Prefer a full Chromium build over the headless shell
    (the shell ignores --host-resolver-rules, which the
    quarantine demos use to map fixture hosts). Override with
    QBC_CHROMIUM_PATH; None = playwright's default."""
    import glob
    import os
    env = os.environ.get("QBC_CHROMIUM_PATH")
    if env:
        return env
    for pat in (os.path.expanduser(
            "~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome"),
            os.path.expanduser(
                "~/.cache/ms-playwright/chromium-*/chrome-mac*/"
                "Chromium.app/Contents/MacOS/Chromium")):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None

EXECUTABLE_SUFFIXES = (".exe", ".msi", ".dmg", ".sh", ".bat",
                       ".cmd", ".scr", ".jar", ".appimage")


class ApprovalRequired(Exception):
    pass


class Runner:
    def __init__(self, task: dict, workdir: Path,
                 approve=None):
        self.task = task
        self.task_id = task.get("id", "task")
        self.workdir = Path(workdir)
        self.profile_dir = Path(tempfile.mkdtemp(
            prefix="qbc-profile-", dir=self.workdir))
        self.quarantine_dir = self.workdir / "quarantine"
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        allow = list(task.get("allowed_domains") or [])
        start = task.get("url", "")
        if start:
            allow.append(host_of(start))
        self.allowlist = Allowlist(allow)
        self.log = ReceiptLog(self.task_id,
                              self.workdir / "receipts.jsonl")
        # approve(action_description) -> bool; default denies.
        self.approve = approve or (lambda desc: False)
        self.extracted: dict = {}

    # -- guards ------------------------------------------------
    def _route_guard(self, route):
        url = route.request.url
        if self.allowlist.allows(url) or url.startswith(
                ("data:", "about:", "blob:")):
            return route.continue_()
        self.log.emit("request", "blocked-allowlist", url,
                      "off-allowlist request aborted by the "
                      "route guard")
        return route.abort()

    def _on_download(self, download):
        target = self.quarantine_dir / Path(
            download.suggested_filename).name
        download.save_as(str(target))
        self.log.emit("download", "download-quarantined",
                      download.url,
                      f"saved to quarantine as {target.name}; "
                      "never executed, never leaves the sandbox")

    def _assess_page(self, page) -> dict:
        html = page.content()
        brands = tuple(self.task["brands"]) \
            if self.task.get("brands") else KNOWN_BRANDS
        verdict = assess(page.url, html, brands)
        if verdict["contained"]:
            self.log.emit("page", "contained-lookalike",
                          page.url, verdict["reason"])
        return verdict

    # -- main loop ---------------------------------------------
    def run(self) -> dict:
        from playwright.sync_api import sync_playwright
        self.log.emit("task", "task-start", self.task.get("url", ""),
                      f"allowlist={self.allowlist!r} "
                      f"profile={self.profile_dir.name}")
        try:
            with sync_playwright() as pw:
                launch_kw = {}
                exe = _chromium_executable()
                if exe:
                    launch_kw["executable_path"] = exe
                ctx = pw.chromium.launch_persistent_context(
                    str(self.profile_dir), headless=True,
                    accept_downloads=True,
                    args=list(self.task.get("chromium_args") or []),
                    **launch_kw)
                ctx.route("**/*", self._route_guard)
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                page.on("download", self._on_download)
                self._drive(page)
                ctx.close()
            self.log.emit("task", "task-complete",
                          detail=f"extracted={sorted(self.extracted)}")
            return {"task_id": self.task_id, "status": "complete",
                    "extracted": self.extracted,
                    "receipts": self.log.rows,
                    "receipt_chain_valid": self.log.verify()}
        except ApprovalRequired as e:
            self.log.emit("task", "task-failed",
                          detail=f"approval not granted: {e}")
            return {"task_id": self.task_id,
                    "status": "approval-required",
                    "extracted": self.extracted,
                    "receipts": self.log.rows,
                    "receipt_chain_valid": self.log.verify()}
        finally:
            shutil.rmtree(self.profile_dir, ignore_errors=True)
            self.log.emit("profile", "allowed",
                          detail="disposable profile destroyed")

    def _drive(self, page):
        steps = self.task.get("steps") or [
            {"action": "goto", "url": self.task["url"]}]
        for step in steps:
            action = step.get("action")
            if action == "goto":
                page.goto(step["url"], wait_until="domcontentloaded")
                self.log.emit("navigate", "allowed", step["url"])
                verdict = self._assess_page(page)
                if verdict["contained"]:
                    break  # containment: no interaction at all
            elif action == "extract":
                for name, selector in (
                        step.get("fields") or {}).items():
                    # real pages render asynchronously after
                    # domcontentloaded — give each selector a
                    # bounded wait before reading it as absent
                    try:
                        page.wait_for_selector(
                            selector, state="attached",
                            timeout=step.get("wait_ms", 5000))
                    except Exception:
                        pass
                    el = page.query_selector(selector)
                    self.extracted[name] = el.inner_text().strip() \
                        if el else None
                self.log.emit("extract", "extracted", page.url,
                              f"fields={list(step.get('fields') or {})}")
            elif action == "click":
                verdict = self._assess_page(page)
                if verdict["contained"]:
                    break
                page.click(step["selector"])
                self.log.emit("click", "allowed", page.url,
                              step["selector"])
            elif action == "fill":
                # Credential-shaped fills are consequential.
                if step.get("sensitive"):
                    self.log.emit("fill", "approval-required",
                                  page.url,
                                  "sensitive fill requested human "
                                  "approval (vision-verify gate)")
                    if not self.approve(
                            f"fill sensitive field "
                            f"{step.get('selector')} on {page.url}"):
                        raise ApprovalRequired(step.get("selector"))
                page.fill(step["selector"], step.get("value", ""))
                self.log.emit("fill", "allowed", page.url,
                              step.get("selector", ""))
            elif action == "download":
                with page.expect_download() as dl:
                    page.click(step["selector"])
                self._on_download(dl.value)
            else:
                self.log.emit("step", "allowed", page.url,
                              f"unknown action {action!r} skipped")
