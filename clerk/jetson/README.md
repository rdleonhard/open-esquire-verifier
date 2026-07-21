# The Clerk on the Jetson — full-time host

The free automated Clerk, run as a production always-on service on the
Jetson Orin Nano Super (the second Testament reliquary; it also hosts the
`~worbel` Urbit moon, which this leaves untouched).

## What gets installed

| unit | role |
|---|---|
| `clerk.service` | the Clerk on `0.0.0.0:8454`, `Restart=always`, boot-enabled; cache on the NVMe (`/mnt/ssd/clerk-data`, not the SD card) |
| `clerk-health.timer` → `clerk-health.sh` | every 3 min: liveness, at-capacity, thermal, disk — push-alerts the operator on state changes only |
| `clerk-alert@.service` | `OnFailure` handler — pushes an alert if the Clerk unit fails |
| `clerk-boot-notify.service` | pushes "booted" after a reboot |
| `clerk-power.service` + `/usr/local/bin/clerk-power` | power profiles |

Secrets (CourtListener token, ntfy topic) live in
`/mnt/ssd/clerk-data/clerk.env` (mode 600, **never** in the repo).

## Install / update

    git -C /mnt/ssd/open-esquire-verifier pull
    sudo COURTLISTENER_TOKEN=xxxx NTFY_TOPIC=yyyy \
        bash /mnt/ssd/open-esquire-verifier/clerk/jetson/install.sh

Rerun after a `git pull` to pick up new units; an existing `clerk.env` is kept.

## Power — "low power when it needs it"

    clerk-power eco        # 7W   — the Clerk runs fine here
    clerk-power balanced   # 15W  — steady default (headroom for the moon)
    clerk-power full       # MAXN_SUPER — only if something heavy needs it
    clerk-power status

The box shipped pinned at max (25W) to serve a featherweight API. The
default is now **15W**, and the health monitor **auto-drops to 7W if the
SoC crosses 80°C**, restoring 15W once it falls back under 70°C.

## Alerts — how the Jetson reaches you

Push notifications via [ntfy.sh](https://ntfy.sh) — free, no account. On the
first install a private topic is generated; **subscribe to it** to get the
alerts on your phone:

- Phone: install the *ntfy* app (iOS/Android) → Subscribe → your topic name.
- Or open `https://ntfy.sh/<your-topic>` in any browser.

You are paged when the Clerk goes down or recovers, hits CourtListener
capacity, runs hot (and is throttled to eco), or a disk fills. Alerts fire
only on changes, so it stays quiet unless something actually happens. Test:

    /mnt/ssd/open-esquire-verifier/clerk/jetson/clerk-notify.sh "test" default bell

## Going public

The service listens on all interfaces (LAN-reachable). Two ways out to the
open internet, both keeping the token and all data on the Jetson:

**Quick tunnel — no account, no domain, no cost (current):**

    sudo bash /mnt/ssd/open-esquire-verifier/clerk/jetson/install-tunnel.sh

Installs `cloudflared` and a Cloudflare quick tunnel scoped to port 8454
only (not SSH, not the moon). Prints a public `https://…trycloudflare.com`
URL. That URL is **random and changes if the tunnel restarts** — the health
monitor pushes the new one via ntfy, and it's always in
`/mnt/ssd/clerk-data/tunnel-url.txt`. Best-effort; good for a beta.

**Named tunnel — stable, branded (upgrade):** for a permanent address like
`clerk.openesquire.com`, run `cloudflared tunnel login` (one browser login
to a free Cloudflare account, using a domain you already own), create a
named tunnel, and point the ExecStart at it with a `run <name>` config.
Free; the only prerequisite is the domain.
