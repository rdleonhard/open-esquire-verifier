"""Open Esquire Chambers — local HTTP server.

Binds 127.0.0.1 only. The UI (chambers/ui/) talks JSON to /api/*; the native
window (app.py) or any browser points at http://127.0.0.1:8453/.

Port 8453 = Base chain id, easy to remember.
"""
import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import chain
import courtlistener
import store

HOST, PORT = "127.0.0.1", 8453
UI = os.path.join(os.path.dirname(__file__), "ui")
WATCH_S = int(os.environ.get("OE_WATCH_S", "30"))   # watchdog tick

docket = chain.Docket()
_lock = threading.Lock()             # one chain write at a time


def state():
    matters = ([dict(m) for m in docket.pending()] +
               [m for m in store.practice_matters()
                if m["ruling"] == "pending"])
    matters.sort(key=lambda m: m["filedAt"])
    ruled_chain = [m for m in docket.matters if m["ruling"] != "pending"]
    return {
        "chain": {
            "docket": docket.docket,
            "token": docket.token,
            "attorney": docket.attorney,
            "price": docket.price,
            "price_char": docket.price_char,
            "v2": docket.v2,
            "supply": docket.supply,
            "error": docket.error,
            "refreshed": docket.refreshed,
            "rpc": chain.RPC,
        },
        "matters": matters,
        "ruled_chain": ruled_chain,
        "history": store.history(50)[::-1],
        "reputation": docket.reputation(),
        "disclaimer": store.DISCLAIMER,
        "courtlistener_mode": "token" if courtlistener.token() else "anon",
        "settings": store.settings(),
        "in_session": store.in_session(),
        "hours_text": store.hours_text(),
    }


def notify_mac(title, body):
    """Tap the attorney on the shoulder — a real notification, since session
    hours mean someone is actually at this desk."""
    try:
        subprocess.run(
            ["osascript", "-e",
             "display notification %s with title %s sound name \"Glass\""
             % (json.dumps(body[:180]), json.dumps(title[:60]))],
            capture_output=True, timeout=10)
    except Exception:
        pass


_announced = set()          # chain matters we've notified about
_warned = set()             # chain matters past the lapse warning


def _lookup_hint(text):
    """Pre-answer for the arrival notification: what CourtListener says."""
    try:
        cites = courtlistener.lookup(text).get("citations", [])
        if not cites:
            return " — CL: no citation recognized"
        c = cites[0]
        name = c["cases"][0]["name"] if c.get("cases") else ""
        return " — CL: %s%s" % (c["status"].upper().replace("_", " "),
                                " (%s)" % name if name else "")
    except Exception:
        return ""


def watchdog():
    """Auto-deny (= refund) anything pending past the deadline, so the asker
    is never left waiting, and notify the bench when matters arrive or are
    about to lapse. Runs during and outside session hours alike."""
    while True:
        time.sleep(WATCH_S)
        try:
            _watch_once()
        except Exception:
            pass                       # never let the watchdog die


def _refresh_if_needed():
    """One cheap count() probe per tick; the full matter scan only runs when
    the docket grew or something is pending (to catch external rulings)."""
    try:
        n = docket.count()
    except Exception:
        return
    if n != len(docket.matters) or docket.pending():
        docket.refresh()


def _watch_once():
    s = store.settings()
    mins = float(s["auto_deny_minutes"])
    cutoff = time.time() - mins * 60 if mins > 0 else None
    for m in store.practice_matters():
        if cutoff and m["ruling"] == "pending" and m["filedAt"] < cutoff:
            with _lock:
                try:
                    r = store.rule_practice(m["id"], "denied")
                except KeyError:
                    continue           # ruled while we waited on the lock
                store.log_ruling(r, "denied", via="auto")
    _refresh_if_needed()
    for m in docket.pending():
        if m["id"] not in _announced:
            _announced.add(m["id"])
            notify_mac("Open Esquire — citation filed",
                       "%s (%.0f OED): %s%s"
                       % (m["id"], m["paid"] / 1e18, m["text"],
                          _lookup_hint(m["text"])))
        if cutoff is None:
            continue
        left = m["filedAt"] - cutoff
        if left <= 0:
            with _lock:
                if any(x["id"] == m["id"] for x in docket.pending()):
                    receipt = chain.SITE + "#" + m["id"]
                    tx = docket.rule(m["chain_id"], "denied", receipt)
                    store.log_ruling(m, "denied", tx=tx, via="auto")
                    docket.refresh()
                    notify_mac("Open Esquire — matter lapsed",
                               "%s auto-denied; asker refunded." % m["id"])
        elif left <= 600 and m["id"] not in _warned:
            _warned.add(m["id"])
            notify_mac("Open Esquire — lapse warning",
                       "%s auto-refunds in %d min without a ruling."
                       % (m["id"], max(1, int(left / 60))))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):          # quiet; errors still raise
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n) if n else b"{}"
        return json.loads(raw.decode() or "{}")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/state":
            return self._json(state())
        if path == "/":
            path = "/index.html"
        f = os.path.normpath(os.path.join(UI, path.lstrip("/")))
        if f.startswith(UI) and os.path.isfile(f):
            ctype = {"html": "text/html", "css": "text/css",
                     "js": "application/javascript",
                     "svg": "image/svg+xml"}.get(f.rsplit(".", 1)[-1],
                                                 "application/octet-stream")
            data = open(f, "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        try:
            self._post()
        except Exception as e:
            self._json({"error": str(e)[:400]}, 500)

    def _post(self):
        path = self.path.split("?")[0]
        if path == "/api/refresh":
            docket.refresh()
            return self._json(state())
        if path == "/api/lookup":
            body = self._body()
            return self._json(courtlistener.lookup(body.get("text", "")))
        if path == "/api/practice":
            body = self._body()
            text = (body.get("text") or "").strip()
            if not text:
                return self._json({"error": "citation text required"}, 400)
            return self._json(store.file_practice("cite", text))
        if path == "/api/rule":
            return self._rule()
        if path == "/api/publish":
            return self._json(store.publish(record=docket.reputation()))
        if path == "/api/settings":
            try:
                store.save_settings(self._body())
            except (ValueError, KeyError, TypeError) as e:
                return self._json({"error": str(e)[:200]}, 400)
            return self._json(state())
        self._json({"error": "not found"}, 404)

    def _rule(self):
        body = self._body()
        mid = body.get("id", "")
        decision = body.get("decision", "")
        response = (body.get("response") or "").strip()
        if decision not in ("verified", "denied", "wrong"):
            return self._json({"error": "bad decision"}, 400)
        if not body.get("attest"):
            return self._json(
                {"error": "ruling requires the personal-capacity "
                          "attestation"}, 400)
        # Characterization matters ruled WRONG must carry the corrected
        # characterization — that's the product the higher fee buys.
        if response:
            response = (response.rstrip() + "\n\n-- " + store.DISCLAIMER)
        with _lock:
            if mid.startswith("P-"):
                m = store.rule_practice(mid, decision, response)
                rec = store.log_ruling(m, decision, response)
                return self._json({"ok": True, "practice": True,
                                   "record": rec})
            m = next((x for x in docket.pending() if x["id"] == mid), None)
            if not m:
                return self._json({"error": "matter %s is not pending "
                                            "(refresh?)" % mid}, 409)
            receipt = chain.SITE + "#" + mid
            tx = docket.rule(m["chain_id"], decision, receipt,
                             response=response)
            rec = store.log_ruling(m, decision, response, tx=tx)
            docket.refresh()
            return self._json({"ok": True, "tx": tx, "receipt": receipt,
                               "record": rec})


def serve(background=True):
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    threading.Thread(target=docket.refresh, daemon=True).start()
    threading.Thread(target=watchdog, daemon=True).start()
    if background:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv
    srv.serve_forever()


if __name__ == "__main__":
    print("Open Esquire Chambers on http://%s:%d/" % (HOST, PORT))
    serve(background=False)
