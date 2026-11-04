import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clerk.allowlist import Allowlist
from clerk.lookalike import assess, levenshtein, looks_like_brand
from clerk.receipts import ReceiptLog


def test_allowlist_deny_by_default():
    a = Allowlist(["example.com", ".shop.example.org"])
    assert a.allows("https://example.com/x")
    assert a.allows("https://a.shop.example.org/")
    assert not a.allows("https://sub.example.com/")
    assert not a.allows("https://evil.com/")
    assert not Allowlist([]).allows("https://example.com/")


def test_receipt_chain_verifies_and_tamper_breaks():
    log = ReceiptLog("t1")
    log.emit("task", "task-start", "https://example.com")
    log.emit("request", "blocked-allowlist", "https://evil.com")
    assert log.verify()
    log.rows[0]["detail"] = "tampered"
    assert not log.verify()


def test_lookalike_typosquat_with_lure_is_contained():
    html = ('<form><input type="password"></form>'
            '<p>Session expired — sign in again</p>')
    v = assess("https://vultrr.com/login", html)
    assert v["contained"] and v["brand"] == "vultr"


def test_brand_itself_is_not_contained():
    html = '<form><input type="password"></form>'
    assert not assess("https://www.vultr.com/login", html)["contained"]


def test_brand_subdomain_trick_without_lure_is_not_contained():
    # distance alone is not enough — a lure must be present
    assert not assess("https://vultr.evil.com/", "<p>hello</p>")["contained"]


def test_edit_distance():
    assert levenshtein("vultr", "vultrr") == 1
    assert levenshtein("github", "githb") == 1
    assert looks_like_brand("vultr-login.evil.com", "vultr")
