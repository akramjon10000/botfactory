from __future__ import annotations

import string
from typing import Any, Dict, Optional

_HEX_CHARS = set(string.hexdigits.lower())

PAYME_ALLOWED_METHODS = {
    "CheckTransaction",
    "CreateTransaction",
    "PerformTransaction",
    "CancelTransaction",
    "CheckPerformTransaction",
    "GetStatement",
}

CLICK_ALLOWED_ACTIONS = {"0", "1"}
UZUM_ALLOWED_STATUSES = {"success", "failed", "pending", "cancelled"}


def _normalize_hex_signature(raw: Any, expected_len: int, prefixes: tuple[str, ...] = ()) -> Optional[str]:
    if raw is None:
        return None

    signature = str(raw).strip().lower()
    if not signature:
        return None

    for prefix in prefixes:
        if signature.startswith(prefix):
            signature = signature[len(prefix):]
            break

    if len(signature) != expected_len:
        return None
    if any(ch not in _HEX_CHARS for ch in signature):
        return None
    return signature


def normalize_sha1_signature(raw: Any) -> Optional[str]:
    return _normalize_hex_signature(raw, expected_len=40, prefixes=("sha1=",))


def normalize_md5_signature(raw: Any) -> Optional[str]:
    return _normalize_hex_signature(raw, expected_len=32)


def normalize_sha256_signature(raw: Any) -> Optional[str]:
    return _normalize_hex_signature(raw, expected_len=64, prefixes=("sha256=", "v1="))


def extract_positive_int(value: Any) -> Optional[int]:
    try:
        parsed = int(str(value).strip())
    except Exception:
        return None
    return parsed if parsed > 0 else None


def extract_payme_order_id(payload: Dict[str, Any]) -> Optional[int]:
    params = payload.get("params")
    if not isinstance(params, dict):
        return None

    account = params.get("account")
    if isinstance(account, dict):
        order_id = account.get("order_id")
    else:
        order_id = None

    if order_id is None:
        order_id = params.get("order_id")

    return extract_positive_int(order_id)


def validate_payme_payload(payload: Dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False

    method = payload.get("method")
    if method not in PAYME_ALLOWED_METHODS:
        return False

    params = payload.get("params")
    if not isinstance(params, dict):
        return False

    if method == "PerformTransaction":
        return extract_payme_order_id(payload) is not None

    return True


def extract_click_order_id(params: Dict[str, Any]) -> Optional[int]:
    return extract_positive_int(params.get("merchant_trans_id"))


def build_click_signature_payload(params: Dict[str, Any]) -> Dict[str, str]:
    return {
        "service_id": str(params.get("service_id", "")).strip(),
        "merchant_id": str(params.get("merchant_id", "")).strip(),
        "amount": str(params.get("amount", "")).strip(),
        "transaction_param": str(
            params.get("merchant_trans_id") if params.get("merchant_trans_id") is not None else params.get("transaction_param", "")
        ).strip(),
    }


def validate_click_payload(params: Dict[str, Any], expected_service_id: str, expected_merchant_id: str) -> bool:
    if not isinstance(params, dict):
        return False

    required = ("sign", "merchant_trans_id", "amount", "service_id", "merchant_id")
    for field in required:
        if not str(params.get(field, "")).strip():
            return False

    if normalize_md5_signature(params.get("sign")) is None:
        return False

    if expected_service_id and str(params.get("service_id", "")).strip() != str(expected_service_id).strip():
        return False

    if expected_merchant_id and str(params.get("merchant_id", "")).strip() != str(expected_merchant_id).strip():
        return False

    action = params.get("action")
    if action is not None and str(action).strip() not in CLICK_ALLOWED_ACTIONS:
        return False

    if extract_click_order_id(params) is None:
        return False

    return True


def extract_uzum_order_id(payload: Dict[str, Any]) -> Optional[int]:
    return extract_positive_int(payload.get("order_id"))


def validate_uzum_payload(payload: Dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False

    status = str(payload.get("status", "")).strip().lower()
    if status not in UZUM_ALLOWED_STATUSES:
        return False

    return extract_uzum_order_id(payload) is not None

