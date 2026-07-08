"""Local state for Open Esquire Chambers.

Lives in ~/Library/Application Support/openesquire-chambers/:
  rulings.jsonl   append-only log of every ruling entered in the app
                  (same schema as the CYD's /sd/rulings.jsonl, plus
                   response/tx/chain fields)
  practice.json   free local matters (never on-chain, never published)

The device SD log and the chain remain authoritative for their own matters;
this store is the app's own record and the source for publishing chambers
rulings to the public docket.
"""
import json
import os
import subprocess
import time

DATA_DIR = os.path.expanduser(
    "~/Library/Application Support/openesquire-chambers")
RULINGS = os.path.join(DATA_DIR, "rulings.jsonl")
PRACTICE = os.path.join(DATA_DIR, "practice.json")
SETTINGS = os.path.join(DATA_DIR, "settings.json")
REPO = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# Session hours: when the attorney is at the bench and rulings are timely.
# auto_deny_minutes: any matter pending longer than this is automatically
# DENIED (= the asker is refunded) so nobody is left waiting or guessing.
# The deadline runs during and outside session hours alike.
DEFAULT_SETTINGS = {
    "days": {"mon": ["09:00", "17:00"], "tue": ["09:00", "17:00"],
             "wed": ["09:00", "17:00"], "thu": ["09:00", "17:00"],
             "fri": ["09:00", "17:00"], "sat": None, "sun": None},
    "auto_deny_minutes": 30,
}

# Draft attestation — the attorney authored/approved this wording in-app;
# it is embedded verbatim in every ruling record and every characterization
# response so the no-relationship terms travel with the work product.
DISCLAIMER = (
    "INDEPENDENT SCHOLARLY ATTESTATION - NOT LEGAL ADVICE. This ruling is a "
    "personal, scholarly attestation about published case law, entered for "
    "a token fee. The verifier acts in an individual capacity and not as an "
    "attorney for, or on behalf of, any requester or other person. No "
    "attorney-client relationship, no privilege, and no duty of "
    "representation is created by submitting a matter, paying a fee, or "
    "receiving a ruling or corrected characterization. Rulings address only "
    "(i) whether a cited authority exists and (ii) whether a stated "
    "characterization fairly reads the cited text; they are not advice "
    "about any person's rights or situation and may not be relied on as "
    "such.")


def _ensure():
    os.makedirs(DATA_DIR, exist_ok=True)


def settings():
    s = dict(DEFAULT_SETTINGS)
    if os.path.exists(SETTINGS):
        try:
            with open(SETTINGS) as f:
                s.update(json.load(f))
        except Exception:
            pass
    return s


def _valid_window(w):
    if w is None:
        return True
    try:
        a, b = w
        for t in (a, b):
            h, m = t.split(":")
            if not (0 <= int(h) <= 23 and 0 <= int(m) <= 59):
                return False
        return a < b
    except Exception:
        return False


def save_settings(new):
    s = settings()
    if "days" in new:
        days = {}
        for k in DAY_KEYS:
            w = new["days"].get(k)
            if not _valid_window(w):
                raise ValueError("bad window for %s" % k)
            days[k] = list(w) if w else None
        s["days"] = days
    if "auto_deny_minutes" in new:
        m = float(new["auto_deny_minutes"])
        if not (0 <= m <= 24 * 60):
            raise ValueError("auto_deny_minutes out of range")
        s["auto_deny_minutes"] = m
    _ensure()
    tmp = SETTINGS + ".tmp"
    with open(tmp, "w") as f:
        json.dump(s, f, indent=1)
    os.replace(tmp, SETTINGS)
    return s


def _mins(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def in_session(ts=None):
    lt = time.localtime(ts if ts is not None else time.time())
    w = settings()["days"].get(DAY_KEYS[lt.tm_wday])
    if not w:
        return False
    now = lt.tm_hour * 60 + lt.tm_min
    return _mins(w[0]) <= now < _mins(w[1])


def hours_text():
    """Human summary, consecutive same-window days grouped:
    'MON-FRI 09:00-17:00 EDT'."""
    days = settings()["days"]
    runs, cur = [], None
    for k in DAY_KEYS:
        w = days.get(k)
        if not w:
            cur = None
            continue
        w = tuple(w)
        if cur and cur[2] == w:
            cur[1] = k
        else:
            cur = [k, k, w]
            runs.append(cur)
    tz = time.strftime("%Z")
    parts = ["%s%s %s-%s" % (a.upper(),
                             "" if a == b else "-" + b.upper(), w[0], w[1])
             for a, b, w in runs]
    return (" · ".join(parts) + " " + tz) if parts else "BY APPOINTMENT"


def practice_matters():
    if os.path.exists(PRACTICE):
        with open(PRACTICE) as f:
            return json.load(f)
    return []


def _save_practice(ms):
    _ensure()
    tmp = PRACTICE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(ms, f, indent=1)
    os.replace(tmp, PRACTICE)


def file_practice(kind, text):
    ms = practice_matters()
    n = 1 + max((int(m["id"].split("-")[1]) for m in ms), default=0)
    m = {"id": "P-%d" % n, "kind": kind, "text": text[:4000],
         "filedAt": int(time.time()), "ruledAt": 0, "ruling": "pending",
         "paid": 0, "chain": False, "asker": "local", "receipt": ""}
    ms.append(m)
    _save_practice(ms)
    return m


def rule_practice(mid, decision, response=""):
    ms = practice_matters()
    for m in ms:
        if m["id"] == mid and m["ruling"] == "pending":
            m["ruling"] = decision
            m["ruledAt"] = int(time.time())
            if response:
                m["response"] = response
            _save_practice(ms)
            return m
    raise KeyError("no pending practice matter %s" % mid)


def log_ruling(matter, decision, response="", tx="", via="chambers"):
    """Append to the chambers ruling log (device-log schema + extras).
    via="auto" marks the watchdog's lapse-denials."""
    _ensure()
    now = time.time()
    rec = {
        "id": matter["id"],
        "kind": matter["kind"],
        "text": matter["text"],
        "decision": decision,
        "via": via,
        "filed": time.strftime("%H:%M:%S", time.localtime(matter["filedAt"])),
        "ruled": time.strftime("%H:%M:%S", time.localtime(now)),
        "date": time.strftime("%Y-%m-%d", time.localtime(now)),
        "chain": bool(matter.get("chain")),
        "disclaimer": DISCLAIMER,
    }
    if response:
        rec["response"] = response
    if tx:
        rec["tx"] = tx
    with open(RULINGS, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def history(n=100):
    if not os.path.exists(RULINGS):
        return []
    with open(RULINGS) as f:
        lines = f.readlines()[-n:]
    return [json.loads(l) for l in lines if l.strip()]


def publish(record=None):
    """Merge chambers' chain-backed rulings into the public docket and run
    the repo's publish.sh (which also pulls the CYD log, commits, pushes).
    Practice rulings never leave this machine."""
    path = os.path.join(REPO, "data", "rulings.json")
    cur = {"rulings": []}
    if os.path.exists(path):
        with open(path) as f:
            cur = json.load(f)
    excluded = set()
    xfile = os.path.join(REPO, "data", "excluded.txt")
    if os.path.exists(xfile):
        excluded = {l.strip() for l in open(xfile) if l.strip()}
    by_id = {r["id"]: r for r in cur.get("rulings", [])}
    added = 0
    for r in history(10000):
        if not r.get("chain") or r["id"] in excluded:
            continue
        pub = {k: r[k] for k in
               ("id", "kind", "text", "decision", "via",
                "filed", "ruled", "date") if k in r}
        if r.get("response"):
            pub["response"] = r["response"]
            pub["disclaimer"] = r.get("disclaimer", DISCLAIMER)
        if pub["id"] not in by_id or by_id[pub["id"]] != pub:
            added += 1
        by_id[pub["id"]] = pub
    if added:
        rulings = sorted(by_id.values(),
                         key=lambda r: (r.get("date", ""), r.get("ruled", "")))
        out = {"updated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "total": len(rulings), "rulings": rulings}
        with open(path, "w") as f:
            json.dump(out, f, indent=1)
    write_policy(record)
    res = subprocess.run(["/bin/bash", os.path.join(REPO, "publish.sh")],
                         capture_output=True, text=True, timeout=180)
    return {"merged": added,
            "publish": (res.stdout + res.stderr).strip()[-500:],
            "ok": res.returncode == 0}


def write_policy(record=None):
    """data/policy.json — the site advertises session hours, the auto-refund
    deadline, and the verifier's on-chain record, so askers never guess."""
    s = settings()
    pol = {
        "hours_text": hours_text(),
        "days": s["days"],
        "auto_deny_minutes": s["auto_deny_minutes"],
        "in_session": in_session(),
        "updated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    if record:
        pol["record"] = record
    with open(os.path.join(REPO, "data", "policy.json"), "w") as f:
        json.dump(pol, f, indent=1)
