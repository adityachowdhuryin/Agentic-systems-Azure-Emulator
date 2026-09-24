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


def extract_invoice_case_id(*texts: str) -> str | None:
    """Find CASE-01 … CASE-12 in subject/body (Zoho Mail invoice tag)."""
    for text in texts:
        if not text:
            continue
        match = re.search(r"\bCASE-(\d{2})\b", text, flags=re.IGNORECASE)
        if not match:
            continue
        case_id = f"CASE-{match.group(1)}"
        if (EMAILS_DIR / f"{case_id}.json").exists():
            return case_id
    return None


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
    live_mail: dict | None = None,
    live_teams: dict | None = None,
    ingress_source: str = "zoho",
    event_type: str = "lead_created",
    requested_by: str = "invoice-mail-ingress",
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
    if live_mail:
        # Real Zoho fields for demo / inbound-mail panel (admission still used pack from)
        inner_payload["mail_from_live"] = live_mail.get("from") or ""
        inner_payload["mail_to"] = live_mail.get("to") or ""
        inner_payload["mail_subject"] = live_mail.get("subject") or inner_payload["mail_subject"]
        inner_payload["mail_body"] = live_mail.get("body") or inner_payload["mail_body"]
        inner_payload["mail_message_id"] = live_mail.get("message_id") or ""
        inner_payload["case_id"] = live_mail.get("case_id") or ""
    if live_teams:
        inner_payload["teams_from"] = live_teams.get("from_name") or ""
        inner_payload["teams_from_id"] = live_teams.get("from_id") or ""
        inner_payload["teams_text"] = live_teams.get("text") or ""
        inner_payload["teams_channel"] = live_teams.get("channel_id") or ""
        inner_payload["teams_team"] = live_teams.get("team_id") or ""
        inner_payload["conversation_id"] = live_teams.get("conversation_id") or ""
        inner_payload["activity_id"] = live_teams.get("activity_id") or ""
        inner_payload["message"] = live_teams.get("text") or ""
        inner_payload["case_id"] = live_teams.get("case_id") or inner_payload.get("case_id") or ""

    payload = IngressPayload(
        source=ingress_source,
        event_type=event_type,
        event_id=event_id,
        tenant_id=tenant_id,
        lead_id=lead_id,
        requested_by=requested_by,
        payload=inner_payload,
    )

    token_claims = {
        "sub": requested_by,
        "tenant_id": tenant_id,
        "role": "zoho-simulator" if ingress_source == "zoho" else "sales-user",
    }

    raw_payload = {
        "source": ingress_source,
        "event_type": event_type,
        "event_id": event_id,
        "tenant_id": tenant_id,
        "lead_id": lead_id,
        "requested_by": requested_by,
        "payload": inner_payload,
        "email_raw": raw_email,
    }
    zoho_signature = None
    if ingress_source == "zoho":
        zoho_signature = sign_zoho_payload(raw_payload)

    result = BandAOrchestrator(db).process(
        payload,
        raw_payload=raw_payload,
        token_claims=token_claims,
        correlation_id=correlation_id,
        zoho_signature=zoho_signature,
        force_sync=force_sync,
    )
    result["document_ref"] = document_ref
    result["supplier_id"] = supplier["supplier_id"]
    result["use_case"] = UseCase.INVOICE_REVIEW.value
    result["arrival_source"] = arrival_source
    case_id = (live_mail or {}).get("case_id") or (live_teams or {}).get("case_id")
    if case_id:
        result["case_id"] = case_id
    return result


def ingest_zoho_tagged_case(
    db: Session,
    *,
    case_id: str,
    live_mail: dict,
    force_sync: bool = True,
) -> dict:
    """Real Zoho Mail with CASE-XX tag → pack fixture + invoice Band B (sync).

    Deprecated for live Zoho: prefer ingest_zoho_live_invoice (attachment/body).
    Kept for tests / internal use.
    """
    path = EMAILS_DIR / f"{case_id}.json"
    if not path.exists():
        raise ValidationError(f"Unknown case email: {case_id}")
    raw_email = dict(json.loads(path.read_text()))
    zoho_mid = (live_mail.get("message_id") or "").strip()
    # Unique event so Zoho resends / CASE player don't collide
    raw_email["message_id"] = f"zoho-mail:{case_id}:{zoho_mid or new_correlation_id()}"
    raw_email["live_mail"] = {
        "from": live_mail.get("from"),
        "to": live_mail.get("to"),
        "subject": live_mail.get("subject"),
        "body": live_mail.get("body"),
        "message_id": zoho_mid,
    }
    meta = {
        "from": live_mail.get("from") or "",
        "to": live_mail.get("to") or "",
        "subject": live_mail.get("subject") or "",
        "body": live_mail.get("body") or "",
        "message_id": zoho_mid,
        "case_id": case_id,
    }
    return ingest_invoice_email_payload(
        db,
        raw_email,
        arrival_source="zoho_mail",
        force_sync=force_sync,
        live_mail=meta,
    )


def ingest_zoho_live_invoice(
    db: Session,
    *,
    live_mail: dict,
    invoice: dict,
    document_ref: str,
    invoice_source: str = "body",
    force_sync: bool = True,
) -> dict:
    """Live Zoho: invoice JSON from attachment or body paste — no local CASE map."""
    from app.band_a.invoice_admission import resolve_supplier_by_id

    supplier_id = str(invoice.get("supplier_id") or "").strip()
    supplier = resolve_supplier_by_id(supplier_id)
    if not supplier:
        raise ValidationError(f"Unknown supplier_id in invoice: {supplier_id or '(missing)'}")

    tenant_id = settings.invoice_tenant_id
    lead_id = invoice_lead_id_for_supplier(supplier["supplier_id"], document_ref)
    _ensure_invoice_lead(db, lead_id=lead_id, supplier=supplier, tenant_id=tenant_id)

    zoho_mid = (live_mail.get("message_id") or "").strip()
    event_id = f"zoho-live:{document_ref}:{zoho_mid or new_correlation_id()}"
    event_id = re.sub(r"\s+", "", event_id)[:120]

    budgets = default_invoice_budgets()
    correlation_id = new_correlation_id()
    sender = live_mail.get("from") or ""
    attachment_filename = ""
    if invoice_source.startswith("attachment:"):
        attachment_filename = invoice_source.split(":", 1)[1].strip()
    invoice_content = json.dumps(invoice, indent=2)
    inner_payload = {
        "use_case": UseCase.INVOICE_REVIEW.value,
        "document_ref": document_ref,
        "supplier_id": supplier["supplier_id"],
        "arrival_source": "zoho_mail",
        "auth_results": {"spf": "pass", "dkim": "pass", "dmarc": "pass", "source": "live_zoho_content"},
        "mail_from": sender,
        "mail_subject": live_mail.get("subject") or "",
        "mail_body": live_mail.get("body") or "",
        "mail_from_live": sender,
        "mail_to": live_mail.get("to") or "",
        "mail_message_id": zoho_mid,
        "live_invoice": True,
        "invoice_content": invoice_content,
        "invoice_source": invoice_source,
        "attachment_filename": attachment_filename,
        **budgets,
    }

    payload = IngressPayload(
        source="zoho",
        event_type="lead_created",
        event_id=event_id,
        tenant_id=tenant_id,
        lead_id=lead_id,
        requested_by="zoho-mail-bridge",
        payload=inner_payload,
    )
    raw_payload = {
        "source": "zoho",
        "event_type": "lead_created",
        "event_id": event_id,
        "tenant_id": tenant_id,
        "lead_id": lead_id,
        "requested_by": "zoho-mail-bridge",
        "payload": inner_payload,
        "live_invoice": invoice,
    }
    token_claims = {
        "sub": "zoho-mail-bridge",
        "tenant_id": tenant_id,
        "role": "zoho-simulator",
    }
    result = BandAOrchestrator(db).process(
        payload,
        raw_payload=raw_payload,
        token_claims=token_claims,
        correlation_id=correlation_id,
        zoho_signature=sign_zoho_payload(raw_payload),
        force_sync=force_sync,
    )
    result["document_ref"] = document_ref
    result["supplier_id"] = supplier["supplier_id"]
    result["use_case"] = UseCase.INVOICE_REVIEW.value
    result["arrival_source"] = "zoho_mail"
    return result


def ingest_teams_live_invoice(
    db: Session,
    *,
    live_teams: dict,
    invoice: dict,
    document_ref: str,
    invoice_source: str = "body",
    force_sync: bool = False,
) -> dict:
    """Live Teams: invoice JSON pasted in chat text — no local CASE map."""
    from app.band_a.invoice_admission import resolve_supplier_by_id

    supplier_id = str(invoice.get("supplier_id") or "").strip()
    supplier = resolve_supplier_by_id(supplier_id)
    if not supplier:
        raise ValidationError(f"Unknown supplier_id in invoice: {supplier_id or '(missing)'}")

    tenant_id = settings.invoice_tenant_id
    lead_id = invoice_lead_id_for_supplier(supplier["supplier_id"], document_ref)
    _ensure_invoice_lead(db, lead_id=lead_id, supplier=supplier, tenant_id=tenant_id)

    activity_id = (live_teams.get("activity_id") or "").strip()
    event_id = f"teams-live:{document_ref}:{activity_id or new_correlation_id()}"
    event_id = re.sub(r"\s+", "", event_id)[:120]

    budgets = default_invoice_budgets()
    correlation_id = new_correlation_id()
    invoice_content = json.dumps(invoice, indent=2)
    requested_by = (
        live_teams.get("from_id")
        or live_teams.get("from_name")
        or "teams-user"
    )
    inner_payload = {
        "use_case": UseCase.INVOICE_REVIEW.value,
        "document_ref": document_ref,
        "supplier_id": supplier["supplier_id"],
        "arrival_source": "teams",
        "auth_results": {"spf": "pass", "dkim": "pass", "dmarc": "pass", "source": "live_teams_content"},
        "teams_from": live_teams.get("from_name") or "",
        "teams_from_id": live_teams.get("from_id") or "",
        "teams_text": live_teams.get("text") or "",
        "teams_channel": live_teams.get("channel_id") or "",
        "teams_team": live_teams.get("team_id") or "",
        "conversation_id": live_teams.get("conversation_id") or "",
        "activity_id": activity_id,
        "message": live_teams.get("text") or "",
        "live_invoice": True,
        "invoice_content": invoice_content,
        "invoice_source": invoice_source,
        "attachment_filename": "",
        **budgets,
    }

    payload = IngressPayload(
        source="teams",
        event_type="qualify_lead_request",
        event_id=event_id,
        tenant_id=tenant_id,
        lead_id=lead_id,
        requested_by=requested_by,
        payload=inner_payload,
    )
    raw_payload = {
        "source": "teams",
        "event_type": "qualify_lead_request",
        "event_id": event_id,
        "tenant_id": tenant_id,
        "lead_id": lead_id,
        "requested_by": requested_by,
        "payload": inner_payload,
        "live_invoice": invoice,
    }
    token_claims = {
        "sub": requested_by,
        "tenant_id": tenant_id,
        "role": "sales-user",
    }
    result = BandAOrchestrator(db).process(
        payload,
        raw_payload=raw_payload,
        token_claims=token_claims,
        correlation_id=correlation_id,
        force_sync=force_sync,
    )
    result["document_ref"] = document_ref
    result["supplier_id"] = supplier["supplier_id"]
    result["use_case"] = UseCase.INVOICE_REVIEW.value
    result["arrival_source"] = "teams"
    return result


SENTINEL_SUPPLIER_ID = "SUP-1001"


def ingest_live_non_invoice(
    db: Session,
    *,
    document: dict,
    document_ref: str,
    invoice_source: str,
    arrival_source: str,
    force_sync: bool = True,
    live_mail: dict | None = None,
    live_teams: dict | None = None,
) -> dict:
    """Unrelated live inbound → invoice_review so Band B can reject with reasoning."""
    from app.band_a.invoice_admission import resolve_supplier_by_id

    supplier = resolve_supplier_by_id(SENTINEL_SUPPLIER_ID)
    if not supplier:
        raise ValidationError(f"Sentinel supplier missing: {SENTINEL_SUPPLIER_ID}")

    tenant_id = settings.invoice_tenant_id
    lead_id = invoice_lead_id_for_supplier(supplier["supplier_id"], document_ref)
    _ensure_invoice_lead(db, lead_id=lead_id, supplier=supplier, tenant_id=tenant_id)

    mid = ""
    if live_mail:
        mid = (live_mail.get("message_id") or "").strip()
    elif live_teams:
        mid = (live_teams.get("activity_id") or "").strip()
    event_id = f"live-noninv:{document_ref}:{mid or new_correlation_id()}"
    event_id = re.sub(r"\s+", "", event_id)[:120]

    budgets = default_invoice_budgets()
    correlation_id = new_correlation_id()
    attachment_filename = str(document.get("attachment_filename") or "")
    if not attachment_filename and invoice_source.startswith("attachment:"):
        attachment_filename = invoice_source.split(":", 1)[1].strip()
    invoice_content = json.dumps(document, indent=2)

    ingress_source = "zoho" if arrival_source == "zoho_mail" else "teams"
    event_type = "lead_created" if ingress_source == "zoho" else "qualify_lead_request"
    requested_by = "zoho-mail-bridge" if ingress_source == "zoho" else (
        (live_teams or {}).get("from_id")
        or (live_teams or {}).get("from_name")
        or "teams-user"
    )

    inner_payload: dict = {
        "use_case": UseCase.INVOICE_REVIEW.value,
        "document_ref": document_ref,
        "supplier_id": supplier["supplier_id"],
        "arrival_source": arrival_source,
        "auth_results": {"spf": "pass", "dkim": "pass", "dmarc": "pass", "source": "live_non_invoice"},
        "live_invoice": True,
        "inbound_kind": "non_invoice",
        "invoice_content": invoice_content,
        "invoice_source": invoice_source,
        "attachment_filename": attachment_filename,
        **budgets,
    }
    if live_mail:
        inner_payload.update(
            {
                "mail_from": live_mail.get("from") or "",
                "mail_subject": live_mail.get("subject") or "",
                "mail_body": live_mail.get("body") or "",
                "mail_from_live": live_mail.get("from") or "",
                "mail_to": live_mail.get("to") or "",
                "mail_message_id": live_mail.get("message_id") or "",
            }
        )
    if live_teams:
        inner_payload.update(
            {
                "teams_from": live_teams.get("from_name") or "",
                "teams_from_id": live_teams.get("from_id") or "",
                "teams_text": live_teams.get("text") or "",
                "teams_channel": live_teams.get("channel_id") or "",
                "teams_team": live_teams.get("team_id") or "",
                "conversation_id": live_teams.get("conversation_id") or "",
                "activity_id": live_teams.get("activity_id") or "",
                "message": live_teams.get("text") or "",
            }
        )

    payload = IngressPayload(
        source=ingress_source,
        event_type=event_type,
        event_id=event_id,
        tenant_id=tenant_id,
        lead_id=lead_id,
        requested_by=requested_by,
        payload=inner_payload,
    )
    raw_payload = {
        "source": ingress_source,
        "event_type": event_type,
        "event_id": event_id,
        "tenant_id": tenant_id,
        "lead_id": lead_id,
        "requested_by": requested_by,
        "payload": inner_payload,
        "live_invoice": document,
    }
    token_claims = {
        "sub": requested_by,
        "tenant_id": tenant_id,
        "role": "zoho-simulator" if ingress_source == "zoho" else "sales-user",
    }
    zoho_signature = sign_zoho_payload(raw_payload) if ingress_source == "zoho" else None
    result = BandAOrchestrator(db).process(
        payload,
        raw_payload=raw_payload,
        token_claims=token_claims,
        correlation_id=correlation_id,
        zoho_signature=zoho_signature,
        force_sync=force_sync,
    )
    result["document_ref"] = document_ref
    result["supplier_id"] = supplier["supplier_id"]
    result["use_case"] = UseCase.INVOICE_REVIEW.value
    result["arrival_source"] = arrival_source
    result["inbound_kind"] = "non_invoice"
    return result


def ingest_teams_tagged_case(
    db: Session,
    *,
    case_id: str,
    live_teams: dict,
    force_sync: bool = False,
) -> dict:
    """Real Teams message with CASE-XX tag → pack fixture; default async for fast bot ack."""
    path = EMAILS_DIR / f"{case_id}.json"
    if not path.exists():
        raise ValidationError(f"Unknown case email: {case_id}")
    raw_email = dict(json.loads(path.read_text()))
    activity_id = (live_teams.get("activity_id") or "").strip()
    raw_email["message_id"] = f"teams:{case_id}:{activity_id or new_correlation_id()}"
    meta = {
        "from_name": live_teams.get("from_name") or "",
        "from_id": live_teams.get("from_id") or "",
        "text": live_teams.get("text") or "",
        "channel_id": live_teams.get("channel_id") or "",
        "team_id": live_teams.get("team_id") or "",
        "conversation_id": live_teams.get("conversation_id") or "",
        "activity_id": activity_id,
        "case_id": case_id,
    }
    requested_by = meta["from_id"] or meta["from_name"] or "teams-user"
    return ingest_invoice_email_payload(
        db,
        raw_email,
        arrival_source="teams",
        force_sync=force_sync,
        live_teams=meta,
        ingress_source="teams",
        event_type="qualify_lead_request",
        requested_by=requested_by,
    )


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
