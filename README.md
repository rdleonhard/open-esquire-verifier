# Open Esquire · Verifier Public Docket

A public, timestamped record of **attorney rulings on AI-presented case law**.

AI models submit citations and characterizations of law for human review. A
licensed attorney rules on each matter from a dedicated hardware verifier (an
ESP32 touchscreen device); every ruling is logged to the device's microSD and
mirrored here.

**Rulings:**

| Stamp | Meaning |
|---|---|
| ✓ VERIFIED | The citation is real and good law in the applicable jurisdiction, or the characterization is accurate |
| ✗ WRONG | Reviewed and found inaccurate, nonexistent, or no longer good law |
| ⊘ DENIED | The attorney declines to answer; the asker is refunded |

**Live docket:** the GitHub Pages site renders [`data/rulings.json`](data/rulings.json).

## How records get here

`./publish.sh` (run on the LAN with the verifier) pulls recent rulings from
the device (`GET /log`), merges them into `data/rulings.json` by docket id,
and pushes. The device's `/sd/rulings.jsonl` remains the authoritative log.

## Roadmap

- Ethereum token-burn oracle: AI models buy and burn a token to place a matter
  on the docket; this public record anchors the ruling.
- Requester authentication and per-matter receipts.

---
*Open Esquire · web3 counsel. This docket records private review work; nothing
here is legal advice to any reader.*
