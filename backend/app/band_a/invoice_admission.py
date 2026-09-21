"""Band A helpers for invoice-review admission (sender → supplier)."""
from __future__ import annotations

import json
from pathlib import Path

from app.config import settings

PACK_ROOT = Path(__file__).resolve().parents[3] / "Assignment_02_Pack" / "06_invoice_review_data"
VENDOR_DIR = PACK_ROOT / "erp" / "vendor_master"


def load_vendor_email_map() -> dict[str, dict]:
    mapping: dict[str, dict] = {}
    if not VENDOR_DIR.exists():
        return mapping
    for path in VENDOR_DIR.glob("*.json"):
        data = json.loads(path.read_text())
        email = (data.get("remittance_email") or "").strip().lower()
        if email:
            mapping[email] = data
    return mapping


def auth_results_ok(auth: dict | None) -> bool:
    if not auth:
        return False
    return all(
        str(auth.get(k, "")).lower() == "pass" for k in ("spf", "dkim", "dmarc")
    )


def resolve_supplier_from_sender(sender_email: str) -> dict | None:
    email = (sender_email or "").strip().lower()
    # Strip display-name wrappers: "Name <email>"
    if "<" in email and ">" in email:
        email = email.split("<", 1)[1].split(">", 1)[0].strip()
    return load_vendor_email_map().get(email)


def invoice_lead_id_for_supplier(supplier_id: str, document_ref: str) -> str:
    """Stable-ish lead id per document so dedupe/active-run work per invoice."""
    safe = "".join(c if c.isalnum() else "-" for c in document_ref)[:40]
    return f"INV-{supplier_id}-{safe}".upper()[:64]


def default_invoice_budgets() -> dict:
    return {
        "budget_turns": settings.invoice_budget_turns,
        "budget_usd_cents": settings.invoice_budget_usd_cents,
        "budget_seconds": settings.invoice_budget_seconds,
    }
