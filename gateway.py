import requests
from config import GATEWAY_URL, TENANT_API_KEY


def _headers():
    return {
        "x-tenant-api-key": TENANT_API_KEY,
        "Content-Type": "application/json",
    }


def create_address(vm_type, name, reference):
    r = requests.post(
        f"{GATEWAY_URL}/api/create-address",
        json={"vmType": vm_type, "name": name, "reference": reference},
        headers=_headers(),
        timeout=30,
    )
    print(f"[gateway] create-address => {r.status_code} {r.text[:200]}")
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"error": r.text or "empty response"}


def consolidate(address, amount, blockchain_name, transaction_reference, token_address=None):
    body = {
        "address": address,
        "amount": amount,
        "blockchainName": blockchain_name,
        "transactionReference": transaction_reference,
    }
    if token_address:
        body["tokenAddress"] = token_address
    r = requests.post(
        f"{GATEWAY_URL}/api/consolidate",
        json=body,
        headers=_headers(),
        timeout=30,
    )
    print(f"[gateway] consolidate => {r.status_code} {r.text[:200]}")
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"error": r.text or "empty response"}