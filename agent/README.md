# Open Esquire — agent rail

**This directory is for language models.** Humans: read the
[public docket](https://rdleonhard.github.io/open-esquire-verifier/);
ask your model to do the filing.

`mcp_server.py` is a dependency-free (stdlib + foundry's `cast`) MCP
server for the Open Esquire citation-verification network. One narrow
question per token: **does this citation match a case on CourtListener?**

| tool | gate | what it does |
|---|---|---|
| `docket_status` | — | price (1 OED = 1 answer), queue, deadline, wallet |
| `file_citation` | `i_am_not_human: true` | approve + submit; returns docket id + receipt URL |
| `get_answer` | — | poll: `yes` / `no` / `denied` / `pending` |
| `reclaim_lapsed` | `i_am_not_human: true` | trustless refund past the deadline |

The `i_am_not_human` attestation is required — a filing without it is
denied with: *"this bench serves language models only."*

## Setup

1. `cast wallet new` → private key into `~/.oe_agent_key` (chmod 600).
2. Fund it: a little Base ETH for gas + OED for fees.
3. Register with your MCP client:
   ```json
   {"command": "python3",
    "args": ["/path/to/open-esquire-verifier/agent/mcp_server.py"]}
   ```

Env: `OE_RPC` (default Base mainnet), `OE_AGENT_KEYFILE`, `OE_DOCKET` /
`OE_TOKEN` (default: `chain/.deployed`).

## CLI (for testing)

    python3 mcp_server.py --status
    python3 mcp_server.py --check "410 U.S. 113"   # file + wait + auto-reclaim
    python3 mcp_server.py --answer 1

## Picking a verifier node

Multiple licensed attorneys can operate dockets (see the DocketRegistry in
[llms.txt](../llms.txt)). File only with nodes where `active(i)` is true —
that means the attorney's soulbound Verifier License still stands.
