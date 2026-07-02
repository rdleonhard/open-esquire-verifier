#!/bin/bash
# Deploy DemoToken + VerifierDocket to Base mainnet.
# Needs: ~/.oe_verifier_deployer (funded attorney/deployer key).
#   ./deploy.sh          # deploy both, print addresses
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.foundry/bin:$PATH"

RPC="${OE_RPC:-https://mainnet.base.org}"
KEYFILE="$HOME/.oe_verifier_deployer"
[ -f "$KEYFILE" ] || { echo "no key file at $KEYFILE" >&2; exit 1; }
KEY="$(cat "$KEYFILE")"

SUPPLY="1000000ether"        # 1,000,000 OED
PRICE="10ether"              # 10 OED escrowed per matter

echo "deploying DemoToken (1M OED)..."
TOKEN=$(forge create src/DemoToken.sol:DemoToken \
  --rpc-url "$RPC" --private-key "$KEY" --broadcast --json \
  --constructor-args "$(cast to-wei 1000000)" | python3 -c \
  "import json,sys; print(json.load(sys.stdin)['deployedTo'])")
echo "  OED token: $TOKEN"

echo "deploying VerifierDocket (price 10 OED)..."
DOCKET=$(forge create src/VerifierDocket.sol:VerifierDocket \
  --rpc-url "$RPC" --private-key "$KEY" --broadcast --json \
  --constructor-args "$TOKEN" "$(cast to-wei 10)" | python3 -c \
  "import json,sys; print(json.load(sys.stdin)['deployedTo'])")
echo "  VerifierDocket: $DOCKET"

echo
echo "next: export OE_DOCKET=$DOCKET and run oracle/bridge.py"
echo "$TOKEN $DOCKET" > .deployed
