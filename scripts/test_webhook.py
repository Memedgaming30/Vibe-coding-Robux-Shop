"""
Local webhook simulator.

Usage:
    python scripts/test_webhook.py
    python scripts/test_webhook.py --status failed
    python scripts/test_webhook.py --twice          # proves idempotency

Reads WEBHOOK_SECRET from .env.
"""
import os
import sys
import json
import hmac
import hashlib
import requests
from dotenv import load_dotenv

load_dotenv()

args = {a.lstrip("-").split("=")[0]: (a.split("=")[1] if "=" in a else True) for a in sys.argv[1:]}

secret = os.environ.get("WEBHOOK_SECRET", "")
if not secret:
    print("Set WEBHOOK_SECRET in .env first.")
    sys.exit(1)

port = os.environ.get("PORT", "5000")
status = args.get("status", "confirmed")
ref = args.get("reference", f"test-{os.urandom(4).hex()}-consolidate")

payload = {
    "fromAddress": "0x1111111111111111111111111111111111111111",
    "toAddress": "0x2222222222222222222222222222222222222222",
    "reference": ref,
    "transactionCompletedAt": "2026-07-29T12:00:00Z",
    "errorMessage": "simulated failure" if status == "failed" else None,
    "type": "consolidate",
    "status": status,
    "operationType": "api",
    "txHash": "0xdeadbeef1234567890abcdef",
    "amount": "10000000000000000000",
    "providerFee": "100000000000000000",
    "netAmount": "9900000000000000000",
    "tenantFee": "0",
    "tokenName": "USDT",
    "tokenAddress": "0x337610d27c682E347C9cD60BD4b3b107C9d34dDd",
    "blockchain": "bsc-testnet",
}

raw = json.dumps(payload)
sig = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()


def send(label):
    r = requests.post(
        f"http://localhost:{port}/webhooks/gateway",
        data=raw,
        headers={
            "Content-Type": "application/json",
            "x-akpay-webhook-signature": sig,
            "User-Agent": "AKPay-Webhooks/1.0",
        },
    )
    print(f"[{label}] server responded {r.status_code}")


send("first")
if args.get("twice"):
    send("replay")

print(f"reference: {ref}")
print(f"check: curl http://localhost:{port}/api/tx-status/{ref}")
