"""CASE email / chat ingress for invoice review — through Band A orchestrator."""
from __future__ import annotations

import json
import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.band_a.invoice_admission import (
    auth_results_ok,
    default_invoice_budgets,
    invoice_lead_id_for_supplier,
    resolve_supplier_from_sender,
)
from app.band_a.orchestrator import BandAOrchestrator
from app.config import settings
from app.correlation import new_correlation_id
from app.database import Lead, LeadStatus, UseCase
from app.exceptions import ValidationError
from app.repositories.base import LeadRepository
from app.schemas import IngressPayload
from app.security import sign_zoho_payload

PACK_ROOT = Path(__file__).resolve().parents[3] / "Assignment_02_Pack" / "06_invoice_review_data"
EMAILS_DIR = PACK_ROOT / "inbound" / "emails"
CHAT_PATH = PACK_ROOT / "inbound" / "chat_queries.json"


def list_case_emails() -> list[dict]:
    rows = []
    for path in sorted(EMAILS_DIR.glob("CASE-*.json")):
        data = json.loads(path.read_text())
        case_id = path.stem
        att = (data.get("attachments") or [{}])[0]
        rows.append(
            {
                "case_id": case_id,
                "message_id": data.get("message_id"),
                "from": data.get("from"),
                "subject": data.get("subject"),
                "document_ref": att.get("document_ref"),
                "auth_results": data.get("auth_results"),
            }
        )
    return rows


def list_chat_queries() -> list[dict]:
    if not CHAT_PATH.exists():
        return []
    return json.loads(CHAT_PATH.read_text()).get("queries", [])


def _ensure_invoice_lead(db: Session, *, lead_id: str, supplier: dict, tenant_id: str) -> Lead:
    leads = LeadRepository(db)
    existing = leads.get_by_lead_id(lead_id)
    if existing:
        return existing
    lead = Lead(
        lead_id=lead_id,
        tenant_id=tenant_id,
        company_name=supplier.get("legal_name") or supplier["supplier_id"],
        industry=supplier.get("primary_category") or "Unknown",
        employee_count=0,
        requirement="Invoice review",
        budget=0,
        contact_name="AP",
        contact_role="Accounts Payable",
        email=supplier.get("remittance_email") or "",
        source="Invoice Email",
        status=LeadStatus.NEW.value,
    )
    db.add(lead)
    db.flush()
    return lead


def ingest_case_email(db: Session, case_id: str, *, force_sync: bool = False) -> dict:
    path = EMAILS_DIR / f"{case_id}.json"
    if not path.exists():
        raise ValidationError(f"Unknown case email: {case_id}")
    raw_email = json.loads(path.read_text())
    return ingest_invoice_email_payload(db, raw_email, arrival_source="case_email", force_sync=force_sync)


def ingest_invoice_email_payload(
    db: Session,
    raw_email: dict,
    *,
    arrival_source: str,
    force_sync: bool = False,
) -> dict:
    auth = raw_email.get("auth_results") or {}
    if not auth_results_ok(auth):
        raise ValidationError("Sender authentication failed (SPF/DKIM/DMARC)")

    sender = raw_email.get("from") or ""
    supplier = resolve_supplier_from_sender(sender)
    if not supplier:
        raise ValidationError(f"Cannot resolve supplier from sender: {sender}")

    attachments = raw_email.get("attachments") or []
    if not attachments:
        raise ValidationError("Invoice email missing attachment / document_ref")
    document_ref = attachments[0].get("document_ref")
    if not document_ref:
        raise ValidationError("Attachment missing document_ref")

    tenant_id = settings.invoice_tenant_id
    lead_id = invoice_lead_id_for_supplier(supplier["supplier_id"], document_ref)
    _ensure_invoice_lead(db, lead_id=lead_id, supplier=supplier, tenant_id=tenant_id)

    event_id = str(raw_email.get("message_id") or document_ref)
    # Sanitize event_id for storage uniqueness
    event_id = re.sub(r"\s+", "", event_id)[:120]

    budgets = default_invoice_budgets()
    correlation_id = new_correlation_id()
    inner_payload = {
        "use_case": UseCase.INVOICE_REVIEW.value,
        "document_ref": document_ref,
        "supplier_id": supplier["supplier_id"],
        "arrival_source": arrival_source,
        "auth_results": auth,
        "mail_from": sender,
        "mail_subject": raw_email.get("subject"),
        "mail_body": raw_email.get("body_text"),
        **budgets,
    }
    payload = IngressPayload(
        source="zoho",
        event_type="lead_created",
        event_id=event_id,
        tenant_id=tenant_id,
        lead_id=lead_id,
        requested_by="invoice-mail-ingress",
        payload=inner_payload,
    )

    token_claims = {
        "sub": "invoice-mail-ingress",
        "tenant_id": tenant_id,
        "role": "zoho-simulator",
    }

    raw_payload = {
        "source": "zoho",
        "event_type": "lead_created",
        "event_id": event_id,
        "tenant_id": tenant_id,
        "lead_id": lead_id,
        "payload": inner_payload,
        "email_raw": raw_email,
    }
    signature = sign_zoho_payload(raw_payload)

    result = BandAOrchestrator(db).process(
        payload,
        raw_payload=raw_payload,
        token_claims=token_claims,
        correlation_id=correlation_id,
        zoho_signature=signature,
        force_sync=force_sync,
    )
    result["document_ref"] = document_ref
    result["supplier_id"] = supplier["supplier_id"]
    result["use_case"] = UseCase.INVOICE_REVIEW.value
    return result


def ingest_chat_query(db: Session, case_id: str) -> dict:
    """Chat door: same invoice document as CASE email, sync path, arrival_source=chat."""
    path = EMAILS_DIR / f"{case_id}.json"
    if not path.exists():
        raise ValidationError(f"Unknown case for chat: {case_id}")
    raw_email = json.loads(path.read_text())
    # Unique event id so chat doesn't collide with email dedupe of same message_id
    raw_email = dict(raw_email)
    raw_email["message_id"] = f"chat:{case_id}:{raw_email.get('message_id')}"
    return ingest_invoice_email_payload(
        db, raw_email, arrival_source="chat", force_sync=True
    )
