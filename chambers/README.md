# Open Esquire — Chambers

The verifier's Mac bench. One narrow, durable question per token:
**does this citation match a case on CourtListener?** Matters from the
Base-mainnet CitationDocket appear on the docket, the lookup runs
automatically, and the verifier answers — **YES / DENIED / NO** — with the
escrow burn (answered) or refund (denied) posted on-chain from the app.
1 OED = 1 answer.

The claim is deliberately narrow and never goes stale: it is NOT a
good-law opinion (case law changes constantly), NOT a statement that a
case exists nowhere (unpublished/sealed decisions may not be indexed) —
only whether the citation resolves on CourtListener at ruling time.

**Capacity terms are structural, not decorative:** a persistent banner, a
required per-ruling attestation, and the narrow-attestation terms embedded
verbatim in every ruling record — the verifier acts personally, gives no
legal advice, and forms no attorney-client relationship with anyone.

## Run

    python3 chambers/app.py            # native window (pywebview), or
    python3 chambers/app.py --server   # server only: http://127.0.0.1:8453/
    ./chambers/install_app.sh          # (re)install "Open Esquire Chambers.app"
                                       #   into ~/Applications

Port 8453 = Base chain id. A second launch attaches to the running server.

## Pieces

| file | role |
|---|---|
| `app.py` | entry point: server + native WKWebView window |
| `server.py` | localhost HTTP + JSON API (`/api/state,refresh,lookup,practice,rule,publish`) |
| `chain.py` | `cast`-based Base reads + `rule()` sends; auto-detects VerifierDocketV2 |
| `courtlistener.py` | citation lookup — authenticated citation-lookup API, or anonymous exact-citation search fallback |
| `store.py` | practice matters + `rulings.jsonl` in `~/Library/Application Support/openesquire-chambers/`; public-docket publishing |
| `ui/` | the bench (engraved-letterhead theme) |

## CourtListener

Anonymous mode extracts reporter citations and runs exact-citation searches —
zero hits on a well-formed cite is a strong fabrication signal, and the real
case name is shown so a *misattributed* real citation is caught too. For the
authoritative per-citation endpoint, put a free API token in
`~/.courtlistener_token` (courtlistener.com → profile → API token).

## Chain

Addresses come from `chain/.deployed` (override with `OE_DOCKET` / `OE_TOKEN` /
`OE_RPC`). Ruling a chain matter reads the attorney key from
`~/.oe_verifier_deployer` at send time only. The CYD oracle bridge coexists:
the chain arbitrates — whichever bench rules first wins, and the other skips
the matter on its next cycle.

`chain/src/CitationDocket.sol` is **live on Base mainnet** at
`0x42Fc6DfEA560b0272D2Ab83AE6a30fCF1181e768` (deployed 2026-07-09):
`submit(citation)` escrows 1 OED (300-char cap), YES/NO burn it, DENIED
refunds, and trustless `reclaim(id)` refunds after `maxWaitS` (30 min).
V3-era matters are `CL8453-<n>`. Retired: V2 (`OE8453-*`, per-kind 10/50,
in `.deployed.v2`) and V1 (`B8453-*`, flat 10, in `.deployed.v1`) — both
still have their escrow semantics; V2 has reclaim, V1 does not. The app
detects the contract version automatically.

## Session hours & the refund deadline

Session hours (default Mon–Fri 09:00–17:00 local, editable in the app) are
advertised in the letterhead and published to the public docket
(`data/policy.json`). The **auto-refund deadline** (default 30 minutes,
editable, 0 disables) runs in and out of session alike: any matter pending
longer is automatically **DENIED — the asker is refunded in full** — so no
customer is ever left waiting or guessing. Enforced in three layers:

1. **app watchdog** while Chambers is open;
2. **oracle bridge daemon** 24/7 (reads the same setting; the attorney's
   device tap beats the clock, even past the deadline);
3. **V2 `reclaim()`** on-chain (once deployed): after `maxWaitS`, *anyone* —
   typically the asker — can trigger their own refund, trustlessly.

The clock is strict: a matter being actively reviewed at minute 29 still
lapses at 30. Rule first, then keep reading — or lengthen the deadline.

## Practice matters

`P-<n>` matters are free, local, never on-chain, and never published. Use them
to rehearse the bench or as a no-fee intake for the attorney's own checks.
