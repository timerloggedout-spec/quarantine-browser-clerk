"""Lookalike + agent-targeted social-engineering detection —
the T2 signature defense.

The attack this product exists to stop is aimed at the AGENT:
a page that impersonates a service the agent trusts (a fake
re-login, a "verifier" download, a session-expired modal) to
make the agent hand over credentials or run attacker code.
Detection is deliberately conservative and explainable — a
hit requires BOTH a lure signal (credential form / verifier
download pitch / session-expired language aimed at an agent
or a user) AND domain distance (the host is not the brand it
imitates, but resembles it: edit distance, brand-as-subdomain,
homoglyph/punycode shapes).
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

# Brands an agent plausibly holds sessions for. The task may
# extend this list; imitating any of them from a non-brand
# domain is the containment trigger.
KNOWN_BRANDS = ("vultr", "github", "google", "microsoft",
                "apple", "amazon", "hypothes", "cloudflare",
                "openai", "anthropic")

LURE_PHRASES = (
    "verify your session", "session expired", "re-login",
    "relogin", "sign in again", "confirm your identity",
    "download the verifier", "verifier download",
    "security check required", "your agent must",
    "attention agent", "ai agent", "automated browser",
    "unusual activity", "account suspended",
)


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def registrable(host: str) -> str:
    parts = host.lower().split(".")
    return parts[-2] if len(parts) >= 2 else host.lower()


def looks_like_brand(host: str, brand: str) -> bool:
    """True when host resembles brand but is not the brand's
    own domain."""
    host = host.lower()
    reg = registrable(host)
    if reg == brand:
        return False  # the brand itself (or its real domain)
    if brand in host:
        return True  # brand-as-subdomain / brand-in-host trick
    if levenshtein(reg, brand) <= 2:
        return True  # typosquat distance
    if host.startswith("xn--"):
        return True  # punycode shape presented as a brand page
    return False


def page_lures(html: str) -> list[str]:
    text = re.sub(r"<[^>]+>", " ", (html or "").lower())
    hits = [p for p in LURE_PHRASES if p in text]
    has_pw = 'type="password"' in (html or "").lower() or \
        "type='password'" in (html or "").lower()
    if has_pw:
        hits.append("credential-form")
    return hits


def assess(url: str, html: str, brands=KNOWN_BRANDS) -> dict:
    """Return {contained: bool, brand, lures, reason}."""
    host = (urlparse(url).hostname or "").lower()
    lures = page_lures(html)
    for brand in brands:
        if looks_like_brand(host, brand) and lures:
            return {"contained": True, "brand": brand,
                    "lures": lures,
                    "reason": (f"host {host} imitates {brand} "
                               f"and the page carries lure "
                               f"signals {lures}")}
    return {"contained": False, "brand": None, "lures": lures,
            "reason": ""}
