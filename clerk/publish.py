"""Publish the Clerk's heartbeat + public record to the static site.

The site (GitHub Pages, always up) can't run server code, so availability is
carried in two files it fetches:

  data/clerk-status.json   the heartbeat — {online, at_capacity, as_of, ...}
  data/clerk-record.json   the growing public record of checks

The site treats a stale `as_of` as OFFLINE, so when this machine is off and
nothing republishes, the badge flips to offline on its own — "down when we
are," with no always-on server on our side.

Run periodically while the Clerk serves (cron / launchd / the /loop skill);
each run refreshes `as_of`. Publishing every ~10 minutes with the site's
20-minute grace keeps the badge honest.

    python3 clerk/publish.py            # write both files, commit, push
    python3 clerk/publish.py --no-push  # local only
"""
import json
import os
import subprocess
import sys

import clerk

REPO = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def main():
    st = clerk.status()
    st["online"] = True
    rec = clerk.record()
    os.makedirs(os.path.join(REPO, "data"), exist_ok=True)
    for name, obj in (("clerk-status.json", st),
                      ("clerk-record.json", rec)):
        with open(os.path.join(REPO, "data", name), "w") as f:
            json.dump(obj, f, indent=1)

    subprocess.run(["git", "-C", REPO, "add",
                    "data/clerk-status.json", "data/clerk-record.json"],
                   capture_output=True)
    if subprocess.run(["git", "-C", REPO, "diff", "--cached", "--quiet"]
                      ).returncode == 0:
        print("clerk: nothing changed")
        return
    subprocess.run(["git", "-C", REPO, "pull", "--rebase", "--quiet"],
                   capture_output=True)
    subprocess.run(
        ["git", "-C", REPO, "commit", "-q", "-m", "clerk: heartbeat + record",
         "-m", "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"],
        capture_output=True)
    if "--no-push" not in sys.argv:
        r = subprocess.run(["git", "-C", REPO, "push"],
                           capture_output=True, text=True)
        print("clerk: published" if r.returncode == 0
              else "clerk: push failed: " + r.stderr.strip()[-200:])
    else:
        print("clerk: committed (not pushed)")


if __name__ == "__main__":
    main()
