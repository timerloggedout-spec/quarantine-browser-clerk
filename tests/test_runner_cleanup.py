"""Lifecycle guarantees for the quarantine browser runner."""
from __future__ import annotations

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clerk.runner import Runner  # noqa: E402


class _FakePage:
    def on(self, *_args, **_kwargs):
        pass


class _FakeContext:
    def __init__(self):
        self.pages = [_FakePage()]
        self.closed = False

    def route(self, *_args, **_kwargs):
        pass

    def close(self):
        self.closed = True


class _FakePlaywrightManager:
    def __init__(self, context):
        self.context = context

    def __enter__(self):
        chromium = types.SimpleNamespace(
            launch_persistent_context=lambda *_a, **_kw: self.context)
        return types.SimpleNamespace(chromium=chromium)

    def __exit__(self, *_args):
        return False


def test_browser_context_closes_when_runner_step_raises(
        tmp_path, monkeypatch):
    context = _FakeContext()
    playwright_package = types.ModuleType("playwright")
    playwright_sync = types.ModuleType("playwright.sync_api")
    playwright_sync.sync_playwright = (
        lambda: _FakePlaywrightManager(context))
    monkeypatch.setitem(sys.modules, "playwright", playwright_package)
    monkeypatch.setitem(
        sys.modules, "playwright.sync_api", playwright_sync)

    runner = Runner({"id": "cleanup-test",
                     "url": "https://example.com/"}, tmp_path)
    profile = runner.profile_dir

    def fail_step(_page):
        raise RuntimeError("synthetic step failure")

    monkeypatch.setattr(runner, "_drive", fail_step)

    import pytest
    with pytest.raises(RuntimeError, match="synthetic step failure"):
        runner.run()

    assert context.closed
    assert not profile.exists()
