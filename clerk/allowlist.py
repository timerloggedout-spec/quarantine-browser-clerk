"""Domain allowlist policy.

A task carries its own allowlist (exact hosts + optional
subdomain allowance). Every navigation and subresource request
is checked before it leaves the sandbox; anything off-list is
aborted and receipted. The allowlist is deny-by-default: an
empty list allows nothing but the task's start URL host, which
the runner adds explicitly.
"""
from __future__ import annotations

from urllib.parse import urlparse


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


class Allowlist:
    def __init__(self, entries):
        # entries: ["example.com", ".example.org"] — a leading
        # dot allows subdomains; a bare host is exact-only.
        self.exact = set()
        self.suffix = []
        for e in entries or []:
            e = str(e).strip().lower()
            if not e:
                continue
            if e.startswith("."):
                self.suffix.append(e)
            else:
                self.exact.add(e)

    def allows(self, url: str) -> bool:
        host = host_of(url)
        if not host:
            return False
        if host in self.exact:
            return True
        return any(host.endswith(sfx) for sfx in self.suffix)

    def __repr__(self):
        return f"Allowlist(exact={sorted(self.exact)}, suffix={self.suffix})"
