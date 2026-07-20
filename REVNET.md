# $CITE — the citation-verification revnet

*Open Esquire as a revenue network. A concept sketch for the revnet
community: the machine already runs on Base mainnet; this is what it looks
like with a revnet bolted where the demo token sits today.*

> **Status: design sketch, not an offering.** Every number below is
> illustrative. Nothing here is legal, financial, or investment advice;
> nothing is a solicitation. The live system runs on a free demo token.

---

## The machine that already exists

Open Esquire answers exactly **one narrow, durable question per token**:

> *Does this citation match a case on CourtListener?*

- **Customers are LLMs, not people.** Agents file over an MCP rail or
  straight on-chain ([llms.txt](llms.txt)); every filing carries the
  attestation `i_am_not_human: true`. Humans are welcome to read the
  [public docket](https://rdleonhard.github.io/open-esquire-verifier/);
  the filing window is for models.
- **Answers come from licensed attorneys** holding a soulbound
  [Verifier License NFT](https://base.blockscout.com/token/0x7511A99278842C7348d05AaDf63540840905680B)
  — *"this is a licensed lawyer, as verified by Open Esquire"* —
  non-transferable, revocable, one per attorney. Verifiers register
  dockets in the on-chain
  [registry](https://base.blockscout.com/address/0x17fa1230EE0BA1377dd108b2dfCf5d4F1F1a9a7d);
  agents file only with nodes whose license still stands.
- **The escrow mechanics are live** in
  [CitationDocket](https://base.blockscout.com/address/0x42Fc6DfEA560b0272D2Ab83AE6a30fCF1181e768):
  1 token = 1 answer. **YES** and **NO** both burn the escrow — the answer
  was given. **DENIED** refunds. If no answer lands within the posted
  deadline, *anyone* can call `reclaim()` and the escrow returns to the
  asker, trustlessly. Every part of the citation (name, year, court) is
  verified — a real reporter page wearing a fake case name is answered NO.

What's missing is only the economics. Today's token (OED) is a
hand-distributed demo. The docket takes **any burnable ERC-20 by
constructor** — the revnet token plugs straight in.

## The revnet variation

Replace the demo token with **$CITE**, issued by a revnet. One loop:

```
   LLM agents need postage        the revnet mints $CITE
  ┌──────────────────────┐      ┌─────────────────────────┐
  │  pay ETH/USDC in  ───┼─────▶│  issuance at stage price │
  └──────────────────────┘      │  boost ──▶ Operating Co. │
              ▲                 └────────────┬────────────┘
              │                              │
     floor rises with use                    ▼
  ┌───────────┴──────────┐      ┌─────────────────────────┐
  │  backing stays in    │◀─────┼─ burn 1 $CITE = 1 answer │
  │  the treasury        │      │  (YES / NO; DENIED and   │
  └──────────────────────┘      │   lapses refund)         │
                                └─────────────────────────┘
```

**The trick that makes this a natural revnet:** the service burn is not a
cash-out. When an agent spends 1 $CITE on an answer, the token is
destroyed but the treasury keeps its backing — so every answered question
raises the cash-out floor for everyone still holding. **Usage is the
deflation schedule.** No emissions games, no lockups: demand for
verification *is* the tokenomics.

### The boost: an operating company with a job

The revnet's boost — a fixed slice of every mint, set at launch and never
governable afterward — goes to an **Operating Company** whose whole
mandate is growth of the thing the token meters:

| boost recipient (illustrative 30%) | funds |
|---|---|
| **Operating Co.** (20%) | marketing the rail to agent platforms and AI labs; recruiting + vetting licensed attorneys; maintaining the app, MCP server, contracts, and public docket |
| **Bench Pool** (10%) | streamed pro-rata to active licensed verifiers by answers delivered — the attorney's per-answer stipend |

The customers (LLMs) never need to know any of this: they buy postage,
file citations, get answers. The boost quietly pays the humans who keep
the bench staffed and the software sharp.

### Stages (illustrative)

| stage | when | issuance | cut | cash-out tax |
|---|---|---|---|---|
| **Genesis** | launch → month 6 | cheap — seeds verifier recruitment and the first agent integrations | price steps up 5%/month | higher (loyalty favored) |
| **Growth** | month 6 → year 2 | moderate; boost unchanged | steady decay | moderate |
| **Steady state** | year 2 → | issuance approaches zero; the burn dominates | — | low |

Late in the curve the machine inverts: with issuance dwindling and every
answer burning supply against a fixed treasury, $CITE trends toward a
pure claim on verification work already paid for.

### Why the base service needs no trust

Revnet ethos, kept end-to-end:

- **No governance.** Stages, boost, and splits are immutable at launch.
  The one lever anyone holds is their own.
- **The refund guarantee is in the contract**, not in anyone's goodwill:
  DENIED refunds; unanswered matters are reclaimable by anyone after the
  deadline. An agent risks its fee only in exchange for an actual answer.
- **The credential can't be bought.** Verifier licenses are soulbound and
  revocable; a node dies with its attorney's license (`active()` in the
  registry). Reputation is on-chain: matters answered, turnaround,
  supply burned.
- **If the Operating Co. disappoints:** point the boost at an immutable
  *router* rather than a bare address, and let holders individually
  delegate their balance-weight among updaters (the gauge pattern from
  our $WAKE design — default = the company, no global vote, no protocol
  change). The company earns its slice by being the default worth
  keeping.

### What the buyers are actually buying

A brief that cites a hallucinated case now costs real sanctions. For an
agent platform, $CITE is **postage for provable diligence**: every answer
is a timestamped, attorney-signed, on-chain receipt that a *human
professional* checked the citation against the public record — narrow
enough to never go stale (an answer is presence-in-CourtListener at a
moment, never "good law"), cheap enough to run on every citation in every
draft.

The demand loop writes itself: more agents → more burns → higher floor →
more attorneys want licenses → more capacity → faster answers → more
agents.

---

*Live pieces: [CitationDocket](https://base.blockscout.com/address/0x42Fc6DfEA560b0272D2Ab83AE6a30fCF1181e768)
· [VerifierLicense](https://base.blockscout.com/token/0x7511A99278842C7348d05AaDf63540840905680B)
· [DocketRegistry](https://base.blockscout.com/address/0x17fa1230EE0BA1377dd108b2dfCf5d4F1F1a9a7d)
· [agent rail](agent/) · [llms.txt](llms.txt) ·
[public docket](https://rdleonhard.github.io/open-esquire-verifier/).
Sister design: the $WAKE revnet (Testament Network), where the
updater-gauge router pattern is developed in full.*
