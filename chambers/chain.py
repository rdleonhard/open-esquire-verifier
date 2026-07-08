"""Base-mainnet plumbing for Open Esquire Chambers.

Same conventions as chain/oracle/bridge.py: foundry `cast` does all RPC work,
the attorney key stays in ~/.oe_verifier_deployer and is read only at send
time. Reads are free; rule() is the only transaction this module sends.

Detects VerifierDocketV2 (per-kind pricing + attorney response) and falls
back cleanly to the deployed V1 contract.
"""
import json
import os
import subprocess
import time

CAST = os.path.expanduser("~/.foundry/bin/cast")
RPC = os.environ.get("OE_RPC", "https://mainnet.base.org")
KEYFILE = os.path.expanduser("~/.oe_verifier_deployer")
SITE = "https://rdleonhard.github.io/open-esquire-verifier/"
TAG = os.environ.get("OE_TAG", "OE8453")   # V2-era ids; V1 used B8453-<n>
DEPLOYED = os.path.join(os.path.dirname(__file__), "..", "chain", ".deployed")

RULING_NAMES = {0: "pending", 1: "verified", 2: "denied", 3: "wrong"}
RULING_CODES = {"verified": 1, "denied": 2, "wrong": 3}
KIND_NAMES = {0: "review", 1: "cite", 2: "char"}

MATTER_SIG = ("matters(uint256)"
              "((address,uint96,uint64,uint64,uint8,uint8,string,string))")
MATTER_SIG_V2 = ("matters(uint256)"
                 "((address,uint96,uint64,uint64,uint8,uint8,string,string,"
                 "string))")


def addresses():
    """(token, docket) from chain/.deployed, overridable by env."""
    token = os.environ.get("OE_TOKEN", "")
    docket = os.environ.get("OE_DOCKET", "")
    if not (token and docket) and os.path.exists(DEPLOYED):
        parts = open(DEPLOYED).read().split()
        if len(parts) >= 2:
            token = token or parts[0]
            docket = docket or parts[1]
    return token, docket


def _cast_call(to, sig, *args, timeout=30):
    out = subprocess.run(
        [CAST, "call", to, sig, *[str(a) for a in args],
         "--rpc-url", RPC, "--json"],
        capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        raise RuntimeError("cast call failed: %s" % out.stderr.strip()[:200])
    v = json.loads(out.stdout)
    if isinstance(v, list) and len(v) == 1:
        v = v[0]                    # cast --json wraps outputs in a list
    return v


def _num(v):
    return int(v, 0) if isinstance(v, str) else int(v)


class Docket:
    """Cached view of the on-chain VerifierDocket."""

    def __init__(self):
        self.token, self.docket = addresses()
        self.matters = []
        self.price = 0
        self.price_char = 0          # V2 only; == price on V1
        self.v2 = False
        self.attorney = ""
        self.supply = 0
        self.error = ""
        self.refreshed = 0.0

    def refresh(self):
        try:
            self._refresh()
            self.error = ""
        except Exception as e:              # keep last good state, surface why
            self.error = str(e)[:300]
        self.refreshed = time.time()
        return self

    def _refresh(self):
        self.attorney = _cast_call(self.docket, "attorney()(address)")
        self.price = _num(_cast_call(self.docket, "price()(uint256)"))
        try:                                 # V2: per-kind pricing
            self.price_char = _num(
                _cast_call(self.docket, "priceOf(uint8)(uint256)", 2))
            self.v2 = True
        except Exception:
            self.price_char = self.price
            self.v2 = False
        self.supply = _num(
            _cast_call(self.token, "totalSupply()(uint256)"))
        n = _num(_cast_call(self.docket, "count()(uint256)"))
        sig = MATTER_SIG_V2 if self.v2 else MATTER_SIG
        matters = []
        for i in range(n):
            m = _cast_call(self.docket, sig, i)
            matters.append({
                "id": "%s-%d" % (TAG, i),
                "chain_id": i,
                "asker": m[0],
                "paid": _num(m[1]),
                "filedAt": _num(m[2]),
                "ruledAt": _num(m[3]),
                "ruling": RULING_NAMES.get(_num(m[4]), "?"),
                "kind": KIND_NAMES.get(_num(m[5]), "?"),
                "text": m[6],
                "receipt": m[7],
                "response": m[8] if self.v2 else "",
                "chain": True,
            })
        self.matters = matters

    def count(self):
        """Cheap probe: one call, no matter scan."""
        return _num(_cast_call(self.docket, "count()(uint256)"))

    def pending(self):
        return [m for m in self.matters if m["ruling"] == "pending"]

    def rule(self, chain_id, decision, receipt, response=""):
        """Post the attorney's ruling. Burns escrow (or refunds on DENIED).
        On V2 the corrected characterization rides along on-chain."""
        code = RULING_CODES[decision]
        if self.v2:
            sig_args = ["rule(uint256,uint8,string,string)",
                        str(chain_id), str(code), receipt, response]
        else:
            sig_args = ["rule(uint256,uint8,string)",
                        str(chain_id), str(code), receipt]
        with open(KEYFILE) as f:
            key = f.read().strip()
        last = ""
        for attempt in range(3):        # public RPCs race on nonces; retry
            out = subprocess.run(
                [CAST, "send", self.docket, *sig_args,
                 "--rpc-url", RPC, "--private-key", key, "--json"],
                capture_output=True, text=True, timeout=120)
            if out.returncode == 0:
                return json.loads(out.stdout).get("transactionHash", "?")
            last = out.stderr.strip()[:300]
            if "nonce" not in last.lower() and attempt:
                break
            time.sleep(6)
        raise RuntimeError("cast send failed: %s" % last)

    def reputation(self):
        """The attorney's public verifier record, computed from the chain."""
        ruled = [m for m in self.matters if m["ruling"] != "pending"]
        burned = sum(m["paid"] for m in ruled
                     if m["ruling"] in ("verified", "wrong"))
        turns = sorted(m["ruledAt"] - m["filedAt"] for m in ruled
                       if m["ruledAt"] and m["filedAt"])
        return {
            "attorney": self.attorney,
            "ruled": len(ruled),
            "verified": sum(m["ruling"] == "verified" for m in ruled),
            "denied": sum(m["ruling"] == "denied" for m in ruled),
            "wrong": sum(m["ruling"] == "wrong" for m in ruled),
            "burned": burned,
            "median_turnaround_s": turns[len(turns) // 2] if turns else 0,
            "since": min((m["filedAt"] for m in ruled), default=0),
        }
