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

KIND_NAMES = {0: "", 1: "cite", 2: "char"}
RULING_CODES = {"verified": 1, "denied": 2, "wrong": 3}
CAST = os.path.expanduser("~/.foundry/bin/cast")

MATTER_SIG = ("matters(uint256)"
              "((address,uint96,uint64,uint64,uint8,uint8,string,string))")


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


def cast_send(sig, *args):
    with open(KEYFILE) as f:
        key = f.read().strip()
    out = subprocess.run(
        [CAST, "send", DOCKET, sig, *[str(a) for a in args],
         "--rpc-url", RPC, "--private-key", key, "--json"],
        capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError("cast send failed: %s" % out.stderr.strip()[:300])
    receipt = json.loads(out.stdout)
    return receipt.get("transactionHash", "?")


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


def cycle():
    n = _num(cast_call("count()(uint256)"))
    ip = None
    for i in range(int(n)):
        m = cast_call(MATTER_SIG, i)
        # tuple: (asker, paid, filedAt, ruledAt, ruling, kind, text, receipt)
        ruling, kind, text = _num(m[4]), _num(m[5]), m[6]
        if ruling != 0:                      # already ruled on-chain
            continue
        if ip is None:
            ip = device_ip()
            if not ip:
                print("device unreachable; will retry")
                return
        vid = "B-%d" % i
        st = device_get(ip, "/verify?id=" + vid)
        if st.get("unknown"):
            q = urllib.parse.urlencode(
                {"token": DEVICE_TOKEN, "id": vid,
                 "kind": KIND_NAMES.get(kind, "")})
            resp = device_post(ip, "/verify?" + q, text)
            print("filed matter %d on the device: %s" % (i, resp.strip()))
        elif st.get("decision") in RULING_CODES:
            d = st["decision"]
            receipt = SITE + "#" + vid
            tx = cast_send("rule(uint256,uint8,string)",
                           i, RULING_CODES[d], receipt)
            print("matter %d ruled %s on-chain: %s" % (i, d, tx))
            try:
                subprocess.run(["/bin/bash", PUBLISH], timeout=120,
                               capture_output=True)
                print("public docket synced")
            except Exception as e:
                print("publish failed (will sync hourly anyway):", e)


def main():
    if not DOCKET:
        sys.exit("set OE_DOCKET to the VerifierDocket address")
    once = "--once" in sys.argv
    while True:
        try:
            cycle()
        except Exception as e:
            print("cycle error:", e)
        if once:
            break
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
