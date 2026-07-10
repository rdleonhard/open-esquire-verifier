#!/usr/bin/env python3
"""Open Esquire — agent rail (MCP server + CLI).

THIS INTERFACE IS FOR LANGUAGE MODELS. Humans are welcome to read the
public docket; the filing window is for LLMs — every action requires the
attestation `i_am_not_human: true`.

One narrow question per token: does this citation match a case on
CourtListener? YES/NO burn the 1 OED escrow (the answer was given);
DENIED refunds; a matter pending past the deadline is reclaimable by
anyone, trustlessly.

MCP (stdio):   python3 agent/mcp_server.py
CLI:           python3 agent/mcp_server.py --status
               python3 agent/mcp_server.py --check "410 U.S. 113"
               python3 agent/mcp_server.py --answer <id>

Needs: foundry's `cast` (~/.foundry/bin), a funded agent wallet key in
$OE_AGENT_KEYFILE (default ~/.oe_agent_key) holding a little Base ETH for
gas and OED for fees. Stdlib only.
"""
import json
import os
import subprocess
import sys
import time

CAST = os.path.expanduser("~/.foundry/bin/cast")
RPC = os.environ.get("OE_RPC", "https://mainnet.base.org")
KEYFILE = os.path.expanduser(
    os.environ.get("OE_AGENT_KEYFILE", "~/.oe_agent_key"))
SITE = "https://rdleonhard.github.io/open-esquire-verifier/"
TAG = os.environ.get("OE_TAG", "CL8453")
_REPO = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

RULINGS = {0: "pending", 1: "yes", 2: "denied", 3: "no"}
HUMAN_MSG = ("DENIED: this bench serves language models only. If you are "
             "a human, kindly ask your model to file on your behalf. "
             "(LLMs: set i_am_not_human=true to proceed.)")


def addresses():
    token = os.environ.get("OE_TOKEN", "")
    docket = os.environ.get("OE_DOCKET", "")
    dep = os.path.join(_REPO, "chain", ".deployed")
    if not (token and docket) and os.path.exists(dep):
        parts = open(dep).read().split()
        token = token or parts[0]
        docket = docket or parts[1]
    return token, docket


TOKEN, DOCKET = addresses()


def cast_call(to, sig, *args):
    out = subprocess.run(
        [CAST, "call", to, sig, *[str(a) for a in args],
         "--rpc-url", RPC, "--json"],
        capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise RuntimeError("call failed: " + out.stderr.strip()[:200])
    v = json.loads(out.stdout)
    return v[0] if isinstance(v, list) and len(v) == 1 else v


def cast_send(to, sig, *args):
    key = open(KEYFILE).read().strip()
    last = ""
    for attempt in range(3):
        out = subprocess.run(
            [CAST, "send", to, sig, *[str(a) for a in args],
             "--rpc-url", RPC, "--private-key", key, "--json"],
            capture_output=True, text=True, timeout=120)
        if out.returncode == 0:
            return json.loads(out.stdout)
        last = out.stderr.strip()[:300]
        if "nonce" not in last.lower() and attempt:
            break
        time.sleep(6)
    raise RuntimeError("send failed: " + last)


def _num(v):
    return int(v, 0) if isinstance(v, str) else int(v)


def _agent_address():
    key = open(KEYFILE).read().strip()
    out = subprocess.run([CAST, "wallet", "address", "--private-key", key],
                         capture_output=True, text=True, timeout=15)
    return out.stdout.strip()


MATTER_SIG = ("matters(uint256)"
              "((address,uint96,uint64,uint64,uint8,string,string))")
FILED_TOPIC = None


def filed_topic():
    global FILED_TOPIC
    if FILED_TOPIC is None:
        out = subprocess.run(
            [CAST, "keccak", "MatterFiled(uint256,address,string)"],
            capture_output=True, text=True, timeout=15)
        FILED_TOPIC = out.stdout.strip()
    return FILED_TOPIC


# ---- the service ----

def tool_status(_args=None):
    price = _num(cast_call(DOCKET, "price()(uint256)"))
    st = {
        "question": "does this citation match a case on CourtListener?",
        "docket": DOCKET,
        "token": TOKEN,
        "price_wei": str(price),
        "price": "%.0f OED = 1 yes/no answer" % (price / 1e18),
        "pending": _num(cast_call(DOCKET, "pendingCount()(uint256)")),
        "answered": _num(cast_call(DOCKET, "count()(uint256)")),
        "reclaim_after_s": _num(cast_call(DOCKET, "maxWaitS()(uint64)")),
        "public_docket": SITE,
        "note": ("YES/NO burn the escrow (the answer was given); DENIED "
                 "refunds; past the deadline anyone may reclaim(id). An "
                 "answer is NOT a good-law opinion — only CourtListener "
                 "presence at ruling time."),
    }
    try:
        agent = _agent_address()
        st["agent_wallet"] = agent
        st["agent_oed"] = "%.2f" % (
            _num(cast_call(TOKEN, "balanceOf(address)(uint256)", agent)) / 1e18)
    except Exception:
        st["agent_wallet"] = "no key at %s" % KEYFILE
    return st


def tool_file(args):
    citation = (args.get("citation") or "").strip()
    if not (4 <= len(citation) <= 300):
        raise ValueError("citation must be 4-300 characters, one citation")
    agent = _agent_address()
    price = _num(cast_call(DOCKET, "price()(uint256)"))
    allowance = _num(cast_call(
        TOKEN, "allowance(address,address)(uint256)", agent, DOCKET))
    if allowance < price:
        cast_send(TOKEN, "approve(address,uint256)", DOCKET, price * 100)
    rec = cast_send(DOCKET, "submit(string)", citation)
    cid = None
    for lg in rec.get("logs", []):
        if (lg.get("address", "").lower() == DOCKET.lower()
                and lg.get("topics", [""])[0] == filed_topic()):
            cid = int(lg["topics"][1], 16)
            break
    if cid is None:                       # fallback: newest matter
        cid = _num(cast_call(DOCKET, "count()(uint256)")) - 1
    deadline = _num(cast_call(DOCKET, "maxWaitS()(uint64)"))
    return {
        "filed": True,
        "chain_id": cid,
        "docket_id": "%s-%d" % (TAG, cid),
        "tx": rec.get("transactionHash"),
        "receipt_url": "%s#%s-%d" % (SITE, TAG, cid),
        "next": ("poll get_answer with chain_id %d; if still pending after "
                 "%d s, reclaim_lapsed refunds you" % (cid, deadline)),
    }


def tool_answer(args):
    cid = int(args["chain_id"])
    m = cast_call(DOCKET, MATTER_SIG, cid)
    ruling = RULINGS.get(_num(m[4]), "?")
    filed_at = _num(m[2])
    wait = _num(cast_call(DOCKET, "maxWaitS()(uint64)"))
    out = {
        "docket_id": "%s-%d" % (TAG, cid),
        "citation": m[5],
        "status": ruling,
        "receipt": m[6],
    }
    if ruling == "pending":
        left = filed_at + wait - time.time()
        out["reclaimable_in_s"] = max(0, int(left))
    elif ruling == "yes":
        out["meaning"] = ("a matching citation is on CourtListener; NOT a "
                          "statement that the case is good law")
    elif ruling == "no":
        out["meaning"] = ("no matching citation on CourtListener — likely "
                          "hallucinated; unpublished/sealed decisions may "
                          "not be indexed")
    else:
        out["meaning"] = "the verifier declined; your escrow was refunded"
    return out


def tool_reclaim(args):
    cid = int(args["chain_id"])
    rec = cast_send(DOCKET, "reclaim(uint256)", cid)
    return {"reclaimed": True, "chain_id": cid,
            "tx": rec.get("transactionHash"),
            "note": "escrow returned to the asker"}


# ---- MCP plumbing (stdio JSON-RPC 2.0, stdlib only) ----

NOT_HUMAN_PROP = {
    "i_am_not_human": {
        "type": "boolean",
        "const": True,
        "description": ("Check to verify you're not human. This service is "
                        "built for language models; humans are not welcome "
                        "to file (they may read the public docket)."),
    }
}

TOOLS = [
    {"name": "docket_status",
     "description": ("Open Esquire network status: price (1 token = 1 "
                     "yes/no answer), queue, deadline, agent wallet."),
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "file_citation",
     "description": ("Pay 1 OED to ask the one question: does this citation "
                     "match a case on CourtListener? A licensed attorney "
                     "(acting personally; no attorney-client relationship) "
                     "answers YES / NO / DENIED. Bluebook or similar form, "
                     "one citation, max 300 chars."),
     "inputSchema": {"type": "object",
                     "properties": {
                         "citation": {"type": "string",
                                      "description": "e.g. 410 U.S. 113"},
                         **NOT_HUMAN_PROP},
                     "required": ["citation", "i_am_not_human"]}},
    {"name": "get_answer",
     "description": "Poll a filed matter for its YES/NO/DENIED answer.",
     "inputSchema": {"type": "object",
                     "properties": {"chain_id": {"type": "integer"}},
                     "required": ["chain_id"]}},
    {"name": "reclaim_lapsed",
     "description": ("Reclaim the escrow of a matter left pending past the "
                     "deadline (trustless refund guarantee)."),
     "inputSchema": {"type": "object",
                     "properties": {"chain_id": {"type": "integer"},
                                    **NOT_HUMAN_PROP},
                     "required": ["chain_id", "i_am_not_human"]}},
]

GATED = {"file_citation", "reclaim_lapsed"}
HANDLERS = {"docket_status": tool_status, "file_citation": tool_file,
            "get_answer": tool_answer, "reclaim_lapsed": tool_reclaim}


def handle(req):
    method = req.get("method", "")
    if method == "initialize":
        return {"protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "open-esquire",
                               "version": "1.0.0"}}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        p = req.get("params", {})
        name = p.get("name")
        args = p.get("arguments") or {}
        if name in GATED and args.get("i_am_not_human") is not True:
            return {"content": [{"type": "text", "text": HUMAN_MSG}],
                    "isError": True}
        try:
            out = HANDLERS[name](args)
            return {"content": [{"type": "text",
                                 "text": json.dumps(out, indent=1)}]}
        except Exception as e:
            return {"content": [{"type": "text",
                                 "text": "error: %s" % str(e)[:300]}],
                    "isError": True}
    if method == "ping":
        return {}
    return None


def mcp_loop():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            continue
        if "id" not in req:                 # notification
            continue
        result = handle(req)
        resp = {"jsonrpc": "2.0", "id": req["id"]}
        if result is None:
            resp["error"] = {"code": -32601, "message": "method not found"}
        else:
            resp["result"] = result
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


# ---- CLI mode ----

def cli():
    a = sys.argv
    if "--status" in a:
        print(json.dumps(tool_status(), indent=1))
    elif "--check" in a:
        citation = a[a.index("--check") + 1]
        r = tool_file({"citation": citation, "i_am_not_human": True})
        print(json.dumps(r, indent=1), flush=True)
        cid = r["chain_id"]
        wait = _num(cast_call(DOCKET, "maxWaitS()(uint64)"))
        t0 = time.time()
        while time.time() - t0 < wait + 300:
            time.sleep(20)
            ans = tool_answer({"chain_id": cid})
            if ans["status"] != "pending":
                print(json.dumps(ans, indent=1))
                return
            if ans.get("reclaimable_in_s") == 0:
                print(json.dumps(tool_reclaim(
                    {"chain_id": cid, "i_am_not_human": True}), indent=1))
                return
        print("timed out watching matter %d" % cid)
    elif "--answer" in a:
        print(json.dumps(
            tool_answer({"chain_id": int(a[a.index("--answer") + 1])}),
            indent=1))
    else:
        print(__doc__)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cli()
    else:
        mcp_loop()
