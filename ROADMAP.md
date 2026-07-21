# Open Esquire — Roadmap

Where the service is going. Live today: the free automated **Clerk**
(citation presence on CourtListener + component checks) and the paid
on-chain **citation docket** (a licensed attorney answers yes/no).

---

## Next: the Approved-Characterization tier

**Citation checks are free when combined with a paid characterization
review by a lawyer.** The automated citation check and the human
characterization review are bundled: the citation check rides along free as
the first step of the paid flow, and it also gates it — no attorney time is
ever spent on a fabricated citation.

Two steps, from the verifier's chair:

1. **Automated citation gate (free).** Orin (the Jetson Clerk) queries the
   CourtListener API for the citation. If it is not there, that comes
   straight back to the requester — fail fast, no lawyer, no charge. This is
   exactly what the Clerk does today.

2. **Human characterization review (paid).** If the citation checks out, the
   matter comes to the attorney, who pulls up the case, reads the opinion,
   and rules on the submitted characterization:
   - **Approve** — the characterization fairly reflects the cited opinion.
   - **Disapprove** — it does not.
   - **Rewrite** — the attorney returns a corrected characterization.
   - **Deny** — the attorney declines to answer (fee refunded).

**The scope is narrow, and it is stated to every requester:**

> We are **NOT** checking whether this case is good law. We are checking
> only whether this **characterization of the cited opinion is approved**.
> Case law changes constantly; whether the case still controls is not what
> this reviews.

### Why this shape

- The citation gate means an attorney never reviews (or a requester never
  pays for) a characterization of a hallucinated citation.
- "This characterization of the cited text is approved" is a claim the
  attorney can stand behind permanently — it is about what the opinion
  *says*, not whether it still *controls*. Same durability logic that
  narrowed the citation service, now applied to characterization: an answer
  never goes stale, so it never becomes a liability the way "this is good
  law" would.
- Bundling free-citation-with-paid-characterization turns the free tier into
  a funnel for the paid one.

### Precedent already built

`VerifierDocketV2` carried a characterization tier (approve / deny / wrong +
an on-chain corrected characterization); it was retired when the service
narrowed to citation-only. This revives it — re-scoped to
**characterization-approval, not good law**, and gated by the now-live free
citation check. The four rulings map cleanly onto the existing bench UI and
escrow semantics (answered → burn, deny → refund).

---

## Also queued

- **Stable public endpoint** — upgrade the Jetson's Cloudflare quick tunnel
  to a named tunnel at **`clerk.openesquire.com`** (branded, stable) before
  marketing in earnest.
- **Wording review** — the attorney/operator signs off on every
  narrow-attestation and disclaimer, including the "not good law" line above.
- **Distribution to LLMs** — MCP registry listings and drop-in agent
  examples so a developer can wire in the check in minutes.
