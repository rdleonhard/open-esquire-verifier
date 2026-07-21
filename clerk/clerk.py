"""The Clerk — free, automated citation checking for Open Esquire.

The Clerk does the ministerial record-check an LLM needs before it trusts a
citation it is about to cite: is this citation actually on CourtListener,
and do its parts (name, year, court) match the reported case? No token, no
human, no judgment — that judgment is the attorney's paid bench, later. The
Clerk just reads the record and reports what it finds.

  clerk  -> free, automated, "is this citation on CourtListener?" (this file)
  bench  -> paid, human, an attorney answers on-chain            (chambers/)

Two levers keep us inside the free CourtListener tier:

  1. a persistent CACHE — a citation is looked up once, then served from
     memory forever. Popular citations cost one API call, ever; and the
     cache is also the point — it is the growing public record of checked
     citations, the history and reliance we are building before the paid
     tier opens.
  2. a BUDGET GOVERNOR — a rolling cap on real CourtListener calls. When the
     window is spent, uncached citations get an honest "at capacity, try
     later" instead of us blowing past the free tier. Cached citations keep
     answering for free.

The component-verification engine itself lives in chambers/courtlistener.py
(name/year/court checks, ON NOTICE) and is reused verbatim.
"""
import json
import os
import re
import sys
import threading
import time

# reuse the exact verification engine the human bench uses
_CHAMBERS = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "chambers"))
if _CHAMBERS not in sys.path:
    sys.path.insert(0, _CHAMBERS)
import courtlistener  # noqa: E402

DATA_DIR = os.environ.get("CLERK_DATA_DIR") or os.path.expanduser(
    "~/Library/Application Support/openesquire-clerk")
CACHE_FILE = os.path.join(DATA_DIR, "cache.json")
CALLS_FILE = os.path.join(DATA_DIR, "calls.json")
STATUS_FILE = os.path.join(DATA_DIR, "status.json")

# Conservative free-tier caps on *real* CourtListener calls (cache hits are
# free and never counted). These are estimates — tune with the env vars if
# CourtListener's limits differ. The point is to stay comfortably under the
# free tier and go honestly "at capacity" rather than pay for overage.
DAILY_CAP = int(os.environ.get("CLERK_DAILY_CAP", "400"))
MINUTE_CAP = int(os.environ.get("CLERK_MINUTE_CAP", "20"))

DISCLAIMER = (
    "Automated record check only: whether this citation appears on "
    "CourtListener at check time. Not legal advice, not a good-law opinion, "
    "and not human-verified. The attorney-verified bench is a separate paid "
    "service.")

_lock = threading.RLock()


def _ensure():
    os.makedirs(DATA_DIR, exist_ok=True)


def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _atomic(path, obj):
    _ensure()
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def _key(citation):
    return re.sub(r"\s+", " ", citation.strip().lower())


# ---- budget governor --------------------------------------------------

def _budget():
    """(minute_used, day_used, minute_ok, day_ok) from the rolling log."""
    now = time.time()
    calls = [t for t in _load(CALLS_FILE, []) if now - t < 86400]
    minute = sum(1 for t in calls if now - t < 60)
    return minute, len(calls), minute < MINUTE_CAP, len(calls) < DAILY_CAP


def _spend():
    now = time.time()
    calls = [t for t in _load(CALLS_FILE, []) if now - t < 86400]
    calls.append(now)
    _atomic(CALLS_FILE, calls)


# ---- the check --------------------------------------------------------

_VERDICTS = {
    "yes": "This citation is on CourtListener and its parts match the "
           "reported case.",
    "no": "No matching citation is on CourtListener — likely a fabricated "
          "citation. (Unpublished or sealed decisions may not be indexed.)",
    "on_notice": "The citation resolves on CourtListener, but part of it "
                 "(name, year, or court) does NOT match the reported case; "
                 "as presented, it does not match a real case.",
    "ambiguous": "The citation matches more than one case on CourtListener; "
                 "a human should disambiguate.",
    "unrecognized": "No standard reporter citation was recognized in the "
                    "text. Submit one citation in Bluebook or similar form.",
    "unavailable": "The Clerk is at capacity right now (free-tier budget "
                   "spent) and this citation is not cached. Try again later.",
}


def _verdict_of(c):
    if c.get("on_notice"):
        return "on_notice"
    return {"found": "yes", "not_found": "no",
            "ambiguous": "ambiguous"}.get(c.get("status"), "ambiguous")


def _slim_case(k):
    return {"name": k.get("name"), "court": k.get("court"),
            "date": k.get("date"), "url": k.get("url")}


def _cache_entry(citation, c, verdict):
    return {
        "cite": citation,
        "verdict": verdict,
        "status": c.get("status"),
        "on_notice": bool(c.get("on_notice")),
        "checks": c.get("checks", []),
        "cases": [_slim_case(k) for k in c.get("cases", [])[:2]],
    }


def _response(entry, cached, as_of):
    v = entry["verdict"]
    return {
        "citation": entry["cite"],
        "verdict": v,
        "summary": _VERDICTS.get(v, ""),
        "on_notice": entry.get("on_notice", False),
        "checks": entry.get("checks", []),
        "cases": entry.get("cases", []),
        "cached": cached,
        "as_of": as_of,
        "source": "courtlistener.com (Free Law Project)",
        "disclaimer": DISCLAIMER,
    }


def check(citation, allow_network=True):
    """Answer one citation. Cache-first; a real lookup only when uncached
    and within budget. Never raises for the caller — errors become an
    'unavailable' verdict."""
    citation = (citation or "").strip()
    if not (3 <= len(citation) <= 400):
        return _response(
            {"cite": citation, "verdict": "unrecognized"}, False, time.time())
    ckey = _key(citation)
    with _lock:
        cache = _load(CACHE_FILE, {})
        hit = cache.get(ckey)
        if hit:
            hit["last"] = time.time()
            hit["count"] = hit.get("count", 1) + 1
            cache[ckey] = hit
            _atomic(CACHE_FILE, cache)
            return _response(hit["entry"], True, hit["last"])

        minute, day, minute_ok, day_ok = _budget()
        if not allow_network or not (minute_ok and day_ok):
            resp = _response({"cite": citation, "verdict": "unavailable"},
                             False, time.time())
            resp["retry_after"] = 60 if not minute_ok else 3600
            return resp

    # network call outside the lock (it can take seconds)
    try:
        result = courtlistener.lookup(citation)
    except Exception as e:
        r = _response({"cite": citation, "verdict": "unavailable"},
                      False, time.time())
        r["detail"] = str(e)[:200]
        return r

    cites = result.get("citations", [])
    if not cites:
        return _response({"cite": citation, "verdict": "unrecognized"},
                         False, time.time())
    c = cites[0]
    verdict = _verdict_of(c)
    entry = _cache_entry(citation, c, verdict)
    now = time.time()
    with _lock:
        _spend()
        cache = _load(CACHE_FILE, {})
        cache[ckey] = {"entry": entry, "first": now, "last": now, "count": 1}
        _atomic(CACHE_FILE, cache)
    return _response(entry, False, now)


# ---- public record + status ------------------------------------------

def record(recent=25):
    """The Clerk's public record: what has been auto-checked. This is the
    history/reliance artifact."""
    cache = _load(CACHE_FILE, {})
    rows = sorted(cache.values(), key=lambda r: r.get("last", 0), reverse=True)
    counts = {}
    total_checks = 0
    for r in cache.values():
        v = r["entry"]["verdict"]
        counts[v] = counts.get(v, 0) + 1
        total_checks += r.get("count", 1)
    return {
        "service": "The Clerk — free automated citation check",
        "distinct_citations": len(cache),
        "checks_served": total_checks,
        "counts": counts,
        "recent": [{
            "cite": r["entry"]["cite"],
            "verdict": r["entry"]["verdict"],
            "case": (r["entry"]["cases"][0]["name"]
                     if r["entry"]["cases"] else ""),
            "count": r.get("count", 1),
            "last": r.get("last", 0),
        } for r in rows[:recent]],
    }


def status():
    minute, day, minute_ok, day_ok = _budget()
    cache = _load(CACHE_FILE, {})
    at_capacity = not (minute_ok and day_ok)
    return {
        "service": "clerk",
        "mode": "free-automated",
        "online": True,                       # written only while running
        "at_capacity": at_capacity,
        "as_of": time.time(),
        "question": "is this citation on CourtListener?",
        "budget": {
            "minute_used": minute, "minute_cap": MINUTE_CAP,
            "day_used": day, "day_cap": DAILY_CAP,
            "note": "cache hits are free and unlimited",
        },
        "cache_count": len(cache),
        "endpoint": "/verify?cite=<citation>",
        "paid_bench": "separate human-verified service (see the docket)",
    }


def write_status():
    _atomic(STATUS_FILE, status())
    return STATUS_FILE
