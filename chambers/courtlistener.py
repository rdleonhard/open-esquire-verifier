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
        "court": hit.get("court") or "",
        "date": hit.get("dateFiled") or hit.get("date_filed") or "",
        "url": BASE + hit["absolute_url"] if hit.get("absolute_url") else "",
        "citations": cites if isinstance(cites, list) else [cites],
    }


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
        citations.append({
            "cite": row.get("citation", "?"),
            "status": ("found" if status == 200 and clusters else
                       "ambiguous" if status == 300 else
                       "not_found" if status == 404 else
                       "error"),
            "detail": row.get("error_message", ""),
            "cases": [_case(c) for c in clusters[:3]],
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
    for cite in extract_citations(text):
        q = urllib.parse.quote('citation:("%s")' % cite)
        try:
            d = _get(BASE + "/api/rest/v4/search/?type=o&q=" + q)
            hits = d.get("results", [])
            citations.append({
                "cite": cite,
                "status": "found" if hits else "not_found",
                "detail": "" if hits else
                          "no published opinion carries this citation",
                "cases": [_case(h) for h in hits[:3]],
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
