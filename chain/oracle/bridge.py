#!/usr/bin/env python3
"""Oracle bridge: Base chain <-> the CYD hardware verifier.

Each cycle (stateless; the chain is the source of truth):
  1. Read every matter on the VerifierDocket contract.
  2. Any PENDING matter not yet on the device -> file it on the CYD docket
     (device id "B-<n>" for on-chain matter n).
  3. Any matter the attorney has ruled on the device -> post rule() on-chain
     with the public-docket receipt URL, then publish the ledger.

Requires: foundry's `cast` on PATH, the attorney key file, LAN access to the
device. Run:  python3 bridge.py [--once]
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.parse

# ---- configuration ----
RPC = os.environ.get("OE_RPC", "https://mainnet.base.org")
DOCKET = os.environ.get("OE_DOCKET", "")          # set after deploy (0x...)
KEYFILE = os.path.expanduser("~/.oe_verifier_deployer")
SITE = "https://rdleonhard.github.io/open-esquire-verifier/"
DEVICE_MAC = "14:33:5c:b:65:54"
DEVICE_TOKEN = "oe-node-2026"
IP_CACHE = os.path.expanduser("~/.cyd_ip")
PUBLISH = os.path.expanduser(
    "~/Library/Application Support/openesquire-docket/publish.sh")
POLL_S = 30
TAG = os.environ.get("OE_TAG", "")        # device/receipt id prefix; if unset,
                                          # picked per contract version below
# Auto-denial deadline: a matter pending longer than this is DENIED on-chain
# (the asker is refunded) so nobody is left waiting on the attorney. Reads
# the Chambers app's setting when present; OE_MAX_WAIT_MIN overrides; 0 off.
CHAMBERS_SETTINGS = os.path.expanduser(
    "~/Library/Application Support/openesquire-chambers/settings.json")

KIND_NAMES = {0: "", 1: "cite", 2: "char"}
RULING_CODES = {"verified": 1, "denied": 2, "wrong": 3}
CAST = os.path.expanduser("~/.foundry/bin/cast")

MATTER_SIG_V1 = ("matters(uint256)"
                 "((address,uint96,uint64,uint64,uint8,uint8,string,string))")
MATTER_SIG_V2 = ("matters(uint256)"
                 "((address,uint96,uint64,uint64,uint8,uint8,string,string,"
                 "string))")
MATTER_SIG_V3 = ("matters(uint256)"
                 "((address,uint96,uint64,uint64,uint8,string,string))")

# Detected at startup. V3 = CitationDocket (one citation, one yes/no answer,
# no kind byte); V2 had per-kind pricing + 4-arg rule; V1 the original.
VERSION = 1
MATTER_SIG = MATTER_SIG_V1


def detect_version():
    global VERSION, MATTER_SIG, TAG
    try:
        cast_call("priceOf(uint8)(uint256)", 2)
        VERSION = 2
    except Exception:
        try:
            cast_call("maxWaitS()(uint64)")
            VERSION = 3
        except Exception:
            VERSION = 1
    MATTER_SIG = {2: MATTER_SIG_V2, 3: MATTER_SIG_V3}.get(
        VERSION, MATTER_SIG_V1)
    if not TAG:
        TAG = {2: "OE8453", 3: "CL8453"}.get(VERSION, "B8453")


def send_rule(i, code, receipt, response=""):
    if VERSION == 2:
        return cast_send("rule(uint256,uint8,string,string)",
                         i, code, receipt, response)
    return cast_send("rule(uint256,uint8,string)", i, code, receipt)


def cast_call(sig, *args):
    out = subprocess.run(
        [CAST, "call", DOCKET, sig, *[str(a) for a in args],
         "--rpc-url", RPC, "--json"],
        capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise RuntimeError("cast call failed: %s" % out.stderr.strip()[:200])
    v = json.loads(out.stdout)
    if isinstance(v, list) and len(v) == 1:
        v = v[0]                    # cast --json wraps the outputs in a list
    return v


def log(*a):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def cast_send(sig, *args):
    with open(KEYFILE) as f:
        key = f.read().strip()
    last = ""
    for attempt in range(3):           # public RPCs race on nonces; retry
        out = subprocess.run(
            [CAST, "send", DOCKET, sig, *[str(a) for a in args],
             "--rpc-url", RPC, "--private-key", key, "--json"],
            capture_output=True, text=True, timeout=120)
        if out.returncode == 0:
            receipt = json.loads(out.stdout)
            return receipt.get("transactionHash", "?")
        last = out.stderr.strip()[:300]
        if "nonce" not in last.lower() and attempt:
            break
        time.sleep(6)
    raise RuntimeError("cast send failed: %s" % last)


def device_ip():
    ip = ""
    if os.path.exists(IP_CACHE):
        ip = open(IP_CACHE).read().strip()
    if ip:
        try:
            urllib.request.urlopen("http://%s/api" % ip, timeout=3)
            return ip
        except Exception:
            pass
    arp = subprocess.run(["arp", "-an"], capture_output=True, text=True)
    for line in arp.stdout.splitlines():
        if DEVICE_MAC in line.lower():
            return line.split("(")[1].split(")")[0]
    return None


def device_get(ip, path):
    with urllib.request.urlopen("http://%s%s" % (ip, path), timeout=8) as r:
        return json.loads(r.read().decode())


def device_post(ip, path, body):
    req = urllib.request.Request("http://%s%s" % (ip, path),
                                 data=body.encode(), method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read().decode()


def _num(v):
    return int(v, 0) if isinstance(v, str) else int(v)


def max_wait_s():
    m = None
    if os.environ.get("OE_MAX_WAIT_MIN"):
        m = float(os.environ["OE_MAX_WAIT_MIN"])
    else:
        try:
            with open(CHAMBERS_SETTINGS) as f:
                m = float(json.load(f).get("auto_deny_minutes", 30))
        except Exception:
            m = 30.0
    return 0 if m <= 0 else m * 60


def auto_deny(i, vid, kind, text, filed_at):
    receipt = SITE + "#" + vid
    tx = send_rule(i, RULING_CODES["denied"], receipt)
    log("matter %d lapsed (past max wait): auto-DENIED, refunded: %s"
        % (i, tx))
    _log_chambers(vid, kind, text, filed_at, tx)


def _log_chambers(vid, kind, text, filed_at, tx):
    """Record the lapse-denial in the Chambers ruling log so the public
    docket receipt URL resolves to a real entry."""
    try:
        path = os.path.expanduser(
            "~/Library/Application Support/openesquire-chambers/rulings.jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        now = time.time()
        rec = {"id": vid, "kind": KIND_NAMES.get(kind, ""), "text": text,
               "decision": "denied", "via": "auto",
               "filed": time.strftime("%H:%M:%S", time.localtime(filed_at)),
               "ruled": time.strftime("%H:%M:%S", time.localtime(now)),
               "date": time.strftime("%Y-%m-%d", time.localtime(now)),
               "chain": True, "tx": tx}
        with open(path, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception as e:
        log("could not log lapse locally (chain is authoritative):", e)


def _publish():
    try:
        subprocess.run(["/bin/bash", PUBLISH], timeout=120,
                       capture_output=True)
        log("public docket synced")
    except Exception as e:
        log("publish failed (will sync hourly anyway):", e)


def cycle():
    n = _num(cast_call("count()(uint256)"))
    ip = None
    dev_ok = True          # stop poking the device after the first failure
    wait = max_wait_s()
    now = time.time()
    for i in range(int(n)):
        m = cast_call(MATTER_SIG, i)
        # V1/V2: (asker, paid, filedAt, ruledAt, ruling, kind, text, ...)
        # V3:    (asker, paid, filedAt, ruledAt, ruling, citation, receipt)
        ruling = _num(m[4])
        kind = 1 if VERSION == 3 else _num(m[5])
        text = m[5] if VERSION == 3 else m[6]
        if ruling != 0:                      # already ruled on-chain
            continue
        vid = "%s-%d" % (TAG, i)
        expired = bool(wait) and (now - _num(m[2])) > wait

        st = None
        if dev_ok:
            if ip is None:
                ip = device_ip()
                if not ip:
                    dev_ok = False
                    log("device unreachable; deadlines still enforced")
            if ip:
                try:
                    st = device_get(ip, "/verify?id=" + vid)
                except Exception as e:
                    dev_ok = False
                    log("device error (%s); deadlines still enforced" % e)

        if st and st.get("decision") in RULING_CODES:
            # the attorney's ruling beats the clock, even past the deadline
            d = st["decision"]
            if VERSION == 2 and kind == 2 and d == "wrong":
                # V2 requires the corrected characterization with a char
                # WRONG ruling — the device tap can't compose one; the
                # matter stays pending for Chambers (and its rewrite editor)
                log("matter %d: char WRONG needs a rewrite — rule it from "
                    "Chambers; leaving pending" % i)
                continue
            receipt = SITE + "#" + vid
            tx = send_rule(i, RULING_CODES[d], receipt)
            log("matter %d ruled %s on-chain: %s" % (i, d, tx))
            _publish()
        elif expired:
            # pending too long: DENY (= refund the asker) per posted policy;
            # runs whether or not the device answered
            auto_deny(i, vid, kind, text, _num(m[2]))
            _publish()
        elif st and st.get("unknown"):
            q = urllib.parse.urlencode(
                {"token": DEVICE_TOKEN, "id": vid,
                 "kind": KIND_NAMES.get(kind, "")})
            resp = device_post(ip, "/verify?" + q, text)
            log("filed matter %d on the device: %s" % (i, resp.strip()))


def main():
    if not DOCKET:
        sys.exit("set OE_DOCKET to the VerifierDocket address")
    once = "--once" in sys.argv
    detect_version()
    log("oracle bridge up: docket %s (V%d) rpc %s tag %s"
        % (DOCKET, VERSION, RPC, TAG))
    while True:
        try:
            cycle()
        except Exception as e:
            log("cycle error:", e)
        if once:
            break
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
