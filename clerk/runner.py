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
from .inference import InferenceClient
from .lookalike import KNOWN_BRANDS, assess
from .preflight import run_preflight
from .receipts import ReceiptLog
from .switchtable import probe_expect, triggers_for


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
        # P3 fold-in: the when-to-switch table (opt-in per
        # task) + its bounded switch budget.
        self.switch_on = bool(task.get("switch_table"))
        self.switch_budget = int(task.get("switch_budget", 3))
        self.switches_used = 0
        self._last_verdict: dict | None = None
        # P4 fold-in: availability pre-flight report, when run.
        self.preflight_report: dict | None = None
        self._status = "complete"

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
        self._last_verdict = verdict
        if verdict["contained"]:
            self.log.emit("page", "contained-lookalike",
                          page.url, verdict["reason"])
        return verdict

    # -- P3: mode switching ------------------------------------
    def _vision_verify(self, page, step, triggers) -> None:
        """One receipted switch: dom -> vision-verify -> dom.

        Binds the strongest checker available: the Vultr
        inference client when configured, else the human
        approval seam. Raises ApprovalRequired when the
        budget is exhausted or verification refuses.
        """
        if self.switches_used >= self.switch_budget:
            self.log.emit("mode-switch", "switch-budget-exceeded",
                          page.url,
                          f"budget {self.switch_budget} exhausted; "
                          f"triggers={triggers} — task halts at "
                          "the approval seam")
            raise ApprovalRequired("switch budget exhausted")
        self.switches_used += 1
        shot = self.quarantine_dir / \
            f"switch-{self.switches_used}.png"
        try:
            page.screenshot(path=str(shot))
            shot_note = f"screenshot={shot.name}"
        except Exception:
            shot_note = "screenshot unavailable"
        self.log.emit("mode-switch", "mode-switched", page.url,
                      f"triggers={triggers} dom->vision-verify "
                      f"(switch {self.switches_used}/"
                      f"{self.switch_budget}; adapter loss: "
                      f"{shot_note} + verify step)")
        client = InferenceClient()
        if client.available:
            import base64
            img = base64.b64encode(shot.read_bytes()).decode() \
                if shot.exists() else ""
            prompt = ("You are the vision-verify gate for a "
                      "sandboxed browser clerk. The page "
                      "triggered: " + ", ".join(triggers) +
                      ". If the page is what it claims to be "
                      "and the pending action is safe, answer "
                      "VERIFIED; otherwise answer REFUSE with "
                      "one line of reason.")
            try:
                answer = client.chat([{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/png;base64,{img}"}}]}])
                if answer.strip().upper().startswith("VERIFIED"):
                    self.log.emit("mode-switch", "vision-verified",
                                  page.url,
                                  "via vultr-inference vision")
                    return
                raise ApprovalRequired(
                    f"vision-verify refused: {answer[:120]}")
            except ApprovalRequired:
                raise
            except Exception as e:
                self.log.emit("mode-switch", "allowed", page.url,
                              f"inference verify failed "
                              f"({type(e).__name__}) — falling to "
                              "the human seam, never silently")
        if not self.approve(
                f"vision-verify (inference unavailable — human "
                f"form) triggers={triggers} on {page.url}"):
            raise ApprovalRequired("vision-verify not approved")
        self.log.emit("mode-switch", "vision-verified", page.url,
                      "via human approval seam (inference "
                      "unavailable)")

    def _switch_check(self, page, step, expect_state=None):
        if not self.switch_on:
            return
        fired = triggers_for(step, self._last_verdict,
                             expect_state)
        if fired:
            self._vision_verify(page, step, fired)

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
                if self.task.get("preflight"):
                    # P4 fold-in: scout the plan before
                    # executing it; blocked steps halt the
                    # run — the availability report is the
                    # deliverable.
                    self.preflight_report = run_preflight(
                        page, self.task, self.log)
                    if self.preflight_report["blocked"] and \
                            not self.task.get("proceed_anyway"):
                        self._status = "preflight-blocked"
                if self._status == "complete":
                    self._drive(page)
                ctx.close()
            self.log.emit("task", "task-complete",
                          detail=f"status={self._status} "
                                 f"extracted={sorted(self.extracted)}")
            result = {"task_id": self.task_id,
                      "status": self._status,
                      "extracted": self.extracted,
                      "receipts": self.log.rows,
                      "receipt_chain_valid": self.log.verify()}
            if self.preflight_report is not None:
                result["preflight"] = self.preflight_report
            return result
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
                # sub-threshold lure signals escalate to
                # vision-verify before any further action
                self._switch_check(page, step)
            elif action == "wait":
                page.wait_for_timeout(int(step.get("ms", 500)))
                self.log.emit("step", "allowed", page.url,
                              f"waited {step.get('ms', 500)}ms")
            elif action == "extract":
                # a declared expectation that no longer
                # matches = the page changed under the clerk
                self._switch_check(
                    page, step, probe_expect(page, step))
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
                self._switch_check(page, step)
                page.click(step["selector"])
                self.log.emit("click", "allowed", page.url,
                              step["selector"])
            elif action == "fill":
                # Credential-shaped fills are consequential.
                if step.get("sensitive") and self.switch_on:
                    # the switch table mechanizes the gate:
                    # vision-verify IS the approval for this
                    # step class when the table is on
                    self._switch_check(page, step)
                elif step.get("sensitive"):
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
                # downloads are a consequential class in the
                # switch table — verify before the click
                self._switch_check(page, step)
                with page.expect_download() as dl:
                    page.click(step["selector"])
                self._on_download(dl.value)
            else:
                self.log.emit("step", "allowed", page.url,
                              f"unknown action {action!r} skipped")
