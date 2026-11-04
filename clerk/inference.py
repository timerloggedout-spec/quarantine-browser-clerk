"""Vultr Serverless Inference client (OpenAI-compatible).

The agent's LLM calls go to api.vultrinference.com/v1 per the
C1·B stack mandate. The key is read from the environment
(VULTR_API_KEY) — never from a file in the repo, never logged.
When no key is present the client reports itself unavailable
and the runner stays in deterministic steps mode (named in
the receipts, never silently substituted).
"""
from __future__ import annotations

import json
import os
import urllib.request

BASE = "https://api.vultrinference.com/v1"


class InferenceClient:
    def __init__(self, model: str | None = None,
                 api_key: str | None = None):
        self.api_key = api_key or os.environ.get("VULTR_API_KEY", "")
        self.model = model or os.environ.get(
            "VULTR_INFERENCE_MODEL", "")

    @property
    def available(self) -> bool:
        return bool(self.api_key and self.model)

    def chat(self, messages, timeout=60) -> str:
        if not self.available:
            raise RuntimeError("vultr inference not configured "
                               "(VULTR_API_KEY / model)")
        body = json.dumps({"model": self.model,
                           "messages": messages}).encode()
        req = urllib.request.Request(
            BASE + "/chat/completions", data=body, headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read())
        return out["choices"][0]["message"]["content"]
