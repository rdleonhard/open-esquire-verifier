#!/usr/bin/env python3
"""Open Esquire Chambers — native entry point.

Starts the local server, then opens a native WKWebView window (pywebview).
Without pywebview it falls back to the default browser.

    python3 app.py            # native window (or browser fallback)
    python3 app.py --server   # server only, no window
"""
import subprocess
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402

URL = "http://%s:%d/" % (server.HOST, server.PORT)


def main():
    if "--server" in sys.argv:
        server.serve(background=False)
        return
    try:
        server.serve(background=True)
    except OSError:
        # port already owned by a running Chambers — just open a window on it
        pass
    try:
        import webview
        webview.create_window(
            "Open Esquire — Chambers", URL,
            width=1200, height=780, min_size=(900, 620),
            background_color="#050608")
        webview.start()
    except ImportError:
        print("pywebview not installed; opening in browser: " + URL)
        subprocess.run(["open", URL])
        try:
            import time
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
