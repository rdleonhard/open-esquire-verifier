"""The Clerk — free automated citation check, HTTP front end.

    GET  /verify?cite=<citation>     -> JSON verdict (free, no auth)
    POST /verify   {"citation": ...} -> same
    GET  /status                     -> availability + budget
    GET  /record                     -> the public record of checks
    GET  /                           -> a one-screen note (for humans)

Built for language models; humans are welcome but the value is machine-side.
Binds 127.0.0.1 by default — set CLERK_HOST=0.0.0.0 to serve a LAN / tunnel.
Port 8454 (the bench sits on 8453).
"""
import json
import os
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import clerk

HOST = os.environ.get("CLERK_HOST", "127.0.0.1")
PORT = int(os.environ.get("CLERK_PORT", "8454"))
HEARTBEAT_S = int(os.environ.get("CLERK_HEARTBEAT_S", "30"))

_NOTE = (
    "The Clerk — free, automated citation checking for Open Esquire.\n\n"
    "One question: is this citation on CourtListener?\n"
    "  GET /verify?cite=Roe v. Wade, 410 U.S. 113 (1973)\n"
    "  GET /status   GET /record\n\n"
    "Built for language models. Not legal advice; not a good-law opinion;\n"
    "not human-verified. See https://rdleonhard.github.io/open-esquire-verifier/\n"
)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200, ctype="application/json"):
        body = (obj if isinstance(obj, bytes)
                else json.dumps(obj, indent=1).encode())
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(b"", code=204, ctype="text/plain")

    def do_GET(self):
        path, _, query = self.path.partition("?")
        q = urllib.parse.parse_qs(query)
        if path == "/verify":
            cite = (q.get("cite") or q.get("citation") or [""])[0]
            return self._send(clerk.check(cite))
        if path == "/status":
            return self._send(clerk.status())
        if path == "/record":
            return self._send(clerk.record())
        if path in ("/", "/index.html"):
            return self._send(_NOTE.encode(), ctype="text/plain")
        self._send({"error": "not found"}, 404)

    def do_POST(self):
        if self.path.split("?")[0] != "/verify":
            return self._send({"error": "not found"}, 404)
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            body = json.loads(raw.decode() or "{}")
        except ValueError:
            return self._send({"error": "bad json"}, 400)
        self._send(clerk.check(body.get("citation") or body.get("cite") or ""))


def _heartbeat():
    while True:
        try:
            clerk.write_status()
        except Exception:
            pass
        time.sleep(HEARTBEAT_S)


def serve(background=False):
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    clerk.write_status()
    threading.Thread(target=_heartbeat, daemon=True).start()
    if background:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv
    srv.serve_forever()


if __name__ == "__main__":
    print("The Clerk on http://%s:%d/  (free automated citation check)"
          % (HOST, PORT))
    serve()
