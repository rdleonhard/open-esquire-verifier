# The Clerk — free, automated citation checking

Free tier for Open Esquire. An LLM pings a citation; the Clerk checks it
against CourtListener itself — **no token, no human, no wait** — and answers
the one question: *is this citation on CourtListener, and do its parts
match?* The paid, human-verified bench (`chambers/`) is the separate premium
tier, coming later. The Clerk exists now to build **history and reliance**:
every check grows a public record.

```
clerk  -> free · automated · record-presence          (this)
bench  -> paid · a licensed attorney answers on-chain  (chambers/)
```

## Run

    python3 clerk/server.py                 # http://127.0.0.1:8454
    CLERK_HOST=0.0.0.0 python3 clerk/server.py   # serve a LAN / tunnel

    GET /verify?cite=Roe v. Wade, 410 U.S. 113 (1973)
    POST /verify  {"citation": "..."}
    GET /status     GET /record

Verdicts: `yes` · `no` · `on_notice` (resolves but name/year/court mismatch)
· `ambiguous` · `unrecognized` · `unavailable` (at capacity).

## Staying inside the free CourtListener tier

Two levers, no overage:

1. **Cache** (`~/Library/Application Support/openesquire-clerk/cache.json`) —
   a citation is looked up once, then served forever with zero API calls.
   Popular citations are free after the first check, and the cache *is* the
   public record.
2. **Budget governor** — a rolling cap on real CourtListener calls
   (`CLERK_DAILY_CAP`, `CLERK_MINUTE_CAP`; conservative estimates, tune to
   the actual tier). When spent, uncached citations return `unavailable`
   with `retry_after`; cached citations keep answering.

## "Down when we are" — the availability signal

The Clerk writes a heartbeat (`status.json`, `as_of` timestamp).
`clerk/publish.py` mirrors it to the always-on site as
`data/clerk-status.json` + `data/clerk-record.json`. The static site
compares `as_of` to now:

- **ONLINE** — heartbeat fresh, budget left.
- **AT CAPACITY** — heartbeat fresh, budget spent (cached cites still answer).
- **OFFLINE** — heartbeat stale (this machine is off; nothing republishes,
  so the badge flips on its own).

Publish on a timer while serving (every ~10 min; site grace is 20 min):

    */10 * * * *  cd /path/to/open-esquire-verifier && python3 clerk/publish.py

## Going public

Reachable on the open internet is a deploy choice: LAN-only for now, or a
Cloudflare Tunnel / Tailscale funnel from an always-on box (Pi, Jetson) that
holds the CourtListener token — keeping the token and the data off any third
party. `llms.txt` documents the endpoint and the status semantics for agents.
