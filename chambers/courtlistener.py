"""CourtListener client for Open Esquire Chambers.

Two modes:
  * token   — POST /api/rest/v4/citation-lookup/ (precise per-citation
              status: found / not found / ambiguous). Free account token
              in ~/.courtlistener_token (or COURTLISTENER_TOKEN env).
  * anon    — the v4 search API still answers anonymously, so with no token
              we extract citations ourselves and run exact-citation
              searches: citation:("410 U.S. 113"). Zero hits on a
              well-formed citation is a strong hallucination signal.

Either way the result shape is the same:
  {"mode": ..., "citations": [{"cite", "status", "cases": [
      {"name", "court", "date", "url", "citations"}]}], "note": ...}
"""
import json
import os
import re
import ssl
import time
import urllib.parse
import urllib.request

# The python.org framework build ships without system root certs wired up;
# certifi provides them (curl works either way, urllib does not).
try:
    import certifi
    _SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL = ssl.create_default_context()

BASE = "https://www.courtlistener.com"
TOKEN_FILE = os.path.expanduser("~/.courtlistener_token")
MAX_CITES = 8

# Common reporter abbreviations; volume + reporter + page. Deliberately
# permissive — a citation we can't parse simply isn't checked automatically
# and the attorney sees that.
_REPORTER = (
    r"(?:U\.\s?S\.|S\.\s?Ct\.|L\.\s?Ed\.(?:\s?2d)?|"
    r"F\.(?:\s?(?:2d|3d|4th|5th|6th|7th|8th|9th))?|"
    r"F\.\s?Supp\.(?:\s?(?:2d|3d|4th))?|"
    r"F\.\s?App'?x\.?|B\.R\.|Fed\.\s?Cl\.|"
    r"[A-Z]{1,4}\.?(?:\s?[A-Z][a-z]{0,4}\.?){0,2}"
    r"\s?(?:2d|3d|4th|5th|6th|7th|8th|9th)?\.?)"
)
CITE_RE = re.compile(r"\b(\d{1,4})\s+(" + _REPORTER + r")\s+(\d{1,5})\b")


def token():
    t = os.environ.get("COURTLISTENER_TOKEN", "")
    if not t and os.path.exists(TOKEN_FILE):
        t = open(TOKEN_FILE).read().strip()
    return t


# ---- component verification -------------------------------------------
# A real reporter page wearing a fake case name is the most dangerous
# hallucination: the citation "resolves", so a bare found/not-found check
# reassures instead of warning. Every part of the claimed citation is
# compared against the reported case: NAME, YEAR, COURT.

_STOP = {"v", "vs", "versus", "the", "of", "in", "re", "ex", "parte",
         "et", "al", "matter", "on", "behalf", "and"}

_NAME_RE = re.compile(
    r"((?:In\s+re|Ex\s+parte|Matter\s+of)\s+[^,;()]{2,70}"
    r"|[A-Z][\w.'&()\- ]{0,70}?\s+vs?\.?\s+[A-Z][\w.'&()\- ]{0,70}?)"
    r"\s*,?\s*$")

_PAREN_RE = re.compile(r"[^()A-Za-z0-9]{0,6}\(([^)]{0,45}?)\s*(\d{4})\)")

_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
             "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
             "eleventh": 11}

_SCOTUS_REPORTERS = ("u.s.", "s. ct.", "s.ct.", "l. ed.", "l.ed.")


def _name_tokens(s):
    toks = re.sub(r"[^\w\s]", " ", (s or "").lower()).split()
    return {t for t in toks if len(t) > 1 and t not in _STOP}


def _claimed(text, start, end, cite):
    """What the filer asserted around the vol-reporter-page span."""
    before = text[:start].rstrip()
    m = _NAME_RE.search(before[-90:])
    name = re.sub(r"\s+", " ", m.group(1)).strip(" ,") if m else ""
    par = _PAREN_RE.match(text[end:end + 60])
    court = par.group(1).strip(" ,") if par else ""
    year = int(par.group(2)) if par else None
    if not court and cite:
        low = cite.lower()
        if any(r in low for r in _SCOTUS_REPORTERS):
            court = "U.S. Supreme Court"    # implied by the reporter
    return {"name": name, "court": court, "year": year}


def _court_ordinal(s):
    s = (s or "").lower()
    m = re.search(r"(\d+)(?:st|nd|rd|th)\s*cir", s)
    if m:
        return ("cir", int(m.group(1)))
    for word, n in _ORDINALS.items():
        if word in s and "circuit" in s:
            return ("cir", n)
    if "d.c. cir" in s or ("district of columbia" in s and "circuit" in s):
        return ("cir", 0)
    if "fed. cir" in s or "federal circuit" in s:
        return ("cir", 13)
    if "supreme court of the united states" in s or "u.s. supreme" in s \
            or s.strip() in ("scotus", "supreme court"):
        return ("scotus", 0)
    return None


def _check_name(claim, case):
    if not claim:
        return None
    ct = _name_tokens(claim)
    if not ct:
        return None
    best = 0.0
    for actual in (case.get("name", ""), case.get("name_full", "")):
        at = _name_tokens(actual)
        if at:
            best = max(best, len(ct & at) / len(ct))
    return best >= 0.5


def _check_year(claim, case):
    if not claim:
        return None
    date = case.get("date") or ""
    if len(date) < 4 or not date[:4].isdigit():
        return None
    return int(date[:4]) == claim


def _check_court(claim, case):
    a, b = _court_ordinal(claim), _court_ordinal(case.get("court", ""))
    if a is None or b is None:
        return None                      # can't parse one side: no alarm
    return a == b


def verify_parts(text, start, end, cite, cases):
    """Per-field checks of the claimed citation against each reported
    case; returns (claim, checks-for-best-case, on_notice)."""
    claim = _claimed(text, start, end, cite)
    if not cases:
        return claim, [], False
    best, best_score = None, -1
    for case in cases:
        checks = []
        for field, fn, actual in (
                ("name", _check_name(claim["name"], case),
                 case.get("name", "")),
                ("year", _check_year(claim["year"], case),
                 (case.get("date") or "")[:4]),
                ("court", _check_court(claim["court"], case),
                 case.get("court", ""))):
            claimed_v = claim[field]
            if fn is None:
                if claimed_v:
                    checks.append({"field": field, "ok": None,
                                   "claimed": str(claimed_v),
                                   "actual": str(actual or "?")})
                continue
            checks.append({"field": field, "ok": bool(fn),
                           "claimed": str(claimed_v),
                           "actual": str(actual or "?")})
        score = sum(1 for c in checks if c["ok"] is True) \
            - 2 * sum(1 for c in checks if c["ok"] is False)
        if best is None or score > best_score:
            best, best_score = checks, score
    on_notice = any(c["ok"] is False for c in best)
    return claim, best, on_notice


def extract_citations(text):
    seen, out = set(), []
    for m in CITE_RE.finditer(text):
        cite = "%s %s %s" % (m.group(1),
                             re.sub(r"\s+", " ", m.group(2)).strip(),
                             m.group(3))
        if cite not in seen:
            seen.add(cite)
            out.append(cite)
    return out[:MAX_CITES]


def _get(url, tok=""):
    req = urllib.request.Request(url, headers={
        "User-Agent": "OpenEsquireChambers/1.0",
        **({"Authorization": "Token " + tok} if tok else {})})
    with urllib.request.urlopen(req, timeout=20, context=_SSL) as r:
        return json.loads(r.read().decode())


def _case(hit):
    cites = hit.get("citation") or []
    return {
        "name": hit.get("caseName") or hit.get("case_name") or "?",
        "name_full": (hit.get("caseNameFull") or hit.get("case_name_full")
                      or ""),
        "court": hit.get("court") or "",
        "date": hit.get("dateFiled") or hit.get("date_filed") or "",
        "url": BASE + hit["absolute_url"] if hit.get("absolute_url") else "",
        "citations": cites if isinstance(cites, list) else [cites],
    }


_court_cache = {}


def _fill_courts(cite, cases):
    """citation-lookup clusters omit the court; one anonymous search per
    citation supplies it (needed for the court check and for display)."""
    if not any(c for c in cases if not c["court"]):
        return
    if cite not in _court_cache:
        try:
            q = urllib.parse.quote('citation:("%s")' % cite)
            d = _get(BASE + "/api/rest/v4/search/?type=o&q=" + q)
            _court_cache[cite] = {
                (h.get("absolute_url") or ""): h.get("court") or ""
                for h in d.get("results", [])}
        except Exception:
            _court_cache[cite] = {}
    by_url = _court_cache[cite]
    default = next(iter(by_url.values()), "") if len(by_url) == 1 else ""
    for c in cases:
        if not c["court"]:
            key = c["url"][len(BASE):] if c["url"].startswith(BASE) else ""
            c["court"] = by_url.get(key, default)


def _lookup_token(text, tok):
    data = urllib.parse.urlencode({"text": text}).encode()
    req = urllib.request.Request(
        BASE + "/api/rest/v4/citation-lookup/", data=data,
        headers={"Authorization": "Token " + tok,
                 "User-Agent": "OpenEsquireChambers/1.0"})
    with urllib.request.urlopen(req, timeout=30, context=_SSL) as r:
        rows = json.loads(r.read().decode())
    citations = []
    for row in rows:
        status = row.get("status")
        clusters = row.get("clusters") or []
        cite = row.get("citation", "?")
        cases = [_case(c) for c in clusters[:3]]
        _fill_courts(cite, cases)
        claim, checks, notice = verify_parts(
            text, row.get("start_index", 0), row.get("end_index", 0),
            cite, cases)
        citations.append({
            "cite": cite,
            "status": ("found" if status == 200 and clusters else
                       "ambiguous" if status == 300 else
                       "not_found" if status == 404 else
                       "error"),
            "detail": row.get("error_message", ""),
            "cases": cases,
            "claim": claim,
            "checks": checks,
            "on_notice": notice,
        })
    # eyecite silently skips reporters it doesn't know — and a nonexistent
    # reporter series ("999 F.9th 123") is the classic hallucination tell.
    # Cross-check against our own extraction and flag anything it missed.
    def _norm(c):
        return re.sub(r"[\s.]", "", c).lower()
    seen = {_norm(c["cite"]) for c in citations}
    for row in rows:
        for n in row.get("normalized_citations") or []:
            seen.add(_norm(n))
    for cite in extract_citations(text):
        if _norm(cite) not in seen:
            citations.append({
                "cite": cite, "status": "not_found",
                "detail": "reporter not recognized by CourtListener — "
                          "no such reporter series; likely fabricated",
                "cases": [],
            })
    return {"mode": "token", "citations": citations, "note": ""}


def _lookup_anon(text):
    citations = []
    seen = set()
    for m in CITE_RE.finditer(text):
        cite = "%s %s %s" % (m.group(1),
                             re.sub(r"\s+", " ", m.group(2)).strip(),
                             m.group(3))
        if cite in seen or len(citations) >= MAX_CITES:
            continue
        seen.add(cite)
        q = urllib.parse.quote('citation:("%s")' % cite)
        try:
            d = _get(BASE + "/api/rest/v4/search/?type=o&q=" + q)
            hits = d.get("results", [])
            cases = [_case(h) for h in hits[:3]]
            claim, checks, notice = verify_parts(
                text, m.start(), m.end(), cite, cases)
            citations.append({
                "cite": cite,
                "status": "found" if hits else "not_found",
                "detail": "" if hits else
                          "no published opinion carries this citation",
                "cases": cases,
                "claim": claim,
                "checks": checks,
                "on_notice": notice,
            })
        except Exception as e:
            citations.append({"cite": cite, "status": "error",
                              "detail": str(e)[:200], "cases": []})
        time.sleep(0.4)              # courtesy to the anonymous rate limit
    note = ("anonymous search fallback — add a free CourtListener API token "
            "to ~/.courtlistener_token for authoritative citation lookup")
    if not citations:
        note = "no recognizable reporter citation in the matter text"
    return {"mode": "anon", "citations": citations, "note": note}


def lookup(text):
    tok = token()
    if tok:
        try:
            return _lookup_token(text, tok)
        except Exception as e:
            res = _lookup_anon(text)
            res["note"] = ("token lookup failed (%s); fell back to "
                           "anonymous search" % str(e)[:120])
            return res
    return _lookup_anon(text)
