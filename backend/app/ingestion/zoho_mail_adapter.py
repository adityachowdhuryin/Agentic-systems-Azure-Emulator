import hashlib
import html
import re
from email.utils import parseaddr
from typing import Any

from sqlalchemy.orm import Session

from app.band_a.orchestrator import BandAOrchestrator
from app.config import settings
from app.ingestion.zoho_adapter import ZohoAdapter
from app.repositories.base import LeadRepository
from app.schemas import IngressPayload, LeadCreate
from app.security import sign_zoho_payload


def _first_str(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _clean_mail_text(value: str) -> str:
    """Decode HTML entities Zoho sometimes sends (&lt;email&gt;) and trim."""
    if not value:
        return ""
    return html.unescape(value).strip()


def _dig(data: dict[str, Any], *paths: str) -> str:
    for path in paths:
        current: Any = data
        for part in path.split("."):
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(part)
        if isinstance(current, str) and current.strip():
            return current.strip()
    return ""


def parse_zoho_mail_payload(raw: dict[str, Any]) -> dict[str, str]:
    """Normalize Zoho Mail / Flow webhook shapes into common email fields."""
    nested = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    message = raw.get("message") if isinstance(raw.get("message"), dict) else {}

    from_addr = _clean_mail_text(
        _first_str(
            raw.get("from"),
            raw.get("fromAddress"),
            raw.get("sender"),
            _dig(raw, "from.address", "from.email"),
            nested.get("from"),
            nested.get("fromAddress"),
            message.get("from"),
        )
    )
    to_addr = _clean_mail_text(
        _first_str(
            raw.get("to"),
            raw.get("toAddress"),
            raw.get("recipient"),
            _dig(raw, "to.address", "to.email"),
            nested.get("to"),
            nested.get("toAddress"),
            message.get("to"),
        )
    )
    subject = _clean_mail_text(
        _first_str(
            raw.get("subject"),
            raw.get("Subject"),
            nested.get("subject"),
            message.get("subject"),
        )
    )
    body = _clean_mail_text(
        _first_str(
            raw.get("body"),
            raw.get("text"),
            raw.get("content"),
            raw.get("plainText"),
            raw.get("summary"),
            nested.get("body"),
            nested.get("text"),
            nested.get("content"),
            message.get("body"),
            message.get("text"),
            message.get("content"),
        )
    )
    message_id = _first_str(
        raw.get("messageId"),
        raw.get("message_id"),
        raw.get("id"),
        raw.get("uid"),
        nested.get("messageId"),
        nested.get("message_id"),
        message.get("messageId"),
        message.get("id"),
    )

    return {
        "from": from_addr,
        "to": to_addr,
        "subject": subject,
        "body": body,
        "message_id": message_id,
    }


def _parse_from_address(from_addr: str) -> tuple[str, str]:
    name, email = parseaddr(from_addr)
    email = email or from_addr
    if not name and "@" in email:
        name = email.split("@", 1)[0].replace(".", " ").title()
    return name or "Unknown Sender", email or "unknown@example.com"


def _company_from_email(email: str) -> str:
    if "@" not in email:
        return "Inbound Mail Lead"
    domain = email.split("@", 1)[1].lower()
    slug = domain.split(".", 1)[0]
    return slug.replace("-", " ").title()


def mail_to_lead_create(parsed: dict[str, str], *, tenant_id: str) -> LeadCreate:
    contact_name, email = _parse_from_address(parsed["from"])
    company_name = _company_from_email(email)
    requirement = parsed["subject"] or "Inbound email inquiry"
    if parsed["body"]:
        requirement = f"{requirement} — {parsed['body'][:240]}"

    return LeadCreate(
        tenant_id=tenant_id,
        company_name=company_name,
        industry="Unknown",
        employee_count=0,
        requirement=requirement[:500],
        budget=0,
        contact_name=contact_name[:128],
        contact_role="Email Contact",
        email=email[:256],
        source="Zoho Mail",
    )


def build_event_id(parsed: dict[str, str]) -> str:
    if parsed["message_id"]:
        safe = re.sub(r"[^a-zA-Z0-9_-]", "-", parsed["message_id"])[:40]
        return f"zoho-mail-{safe}"
    digest = hashlib.sha1(
        f"{parsed['from']}|{parsed['subject']}|{parsed['body'][:120]}".encode()
    ).hexdigest()[:12]
    return f"zoho-mail-{digest}"


class ZohoMailAdapter:
    def __init__(self, db: Session):
        self.db = db
        self.leads = LeadRepository(db)
        self.zoho = ZohoAdapter(db)

    def process_inbound_mail(
        self,
        raw: dict[str, Any],
        *,
        correlation_id: str,
    ) -> dict[str, Any]:
        parsed = parse_zoho_mail_payload(raw)
        lead_data = mail_to_lead_create(parsed, tenant_id=settings.mail_tenant_id)
        lead = self.leads.create(lead_data)
        event_id = build_event_id(parsed)

        inner_payload = {
            "company_name": lead.company_name,
            "industry": lead.industry,
            "employee_count": lead.employee_count,
            "requirement": lead.requirement,
            "budget": lead.budget,
            "contact_name": lead.contact_name,
            "contact_role": lead.contact_role,
            "email": lead.email,
            "mail_from": parsed["from"],
            "mail_to": parsed["to"],
            "mail_subject": parsed["subject"],
            "mail_body": parsed["body"],
            "mail_message_id": parsed["message_id"],
        }
        demo_origin = _first_str(raw.get("demo_origin"))
        if demo_origin:
            inner_payload["demo_origin"] = demo_origin

        payload = {
            "source": "zoho",
            "event_type": "lead_created",
            "event_id": event_id,
            "tenant_id": settings.mail_tenant_id,
            "lead_id": lead.lead_id,
            "payload": inner_payload,
        }
        signature = sign_zoho_payload(payload)
        ingress = IngressPayload(**payload)
        token_claims = {
            "sub": "zoho-mail-bridge",
            "tenant_id": settings.mail_tenant_id,
            "role": "zoho-simulator",
            "aud": settings.jwt_audience,
        }

        orchestrator = BandAOrchestrator(self.db)
        result = orchestrator.process(
            ingress,
            raw_payload=payload,
            token_claims=token_claims,
            correlation_id=correlation_id,
            zoho_signature=signature,
        )

        return {
            "lead_id": lead.lead_id,
            "run_id": result.get("run_id"),
            "state": result.get("state"),
            "event_id": event_id,
            "correlation_id": correlation_id,
            "duplicate": result.get("duplicate", False),
            "rejected": result.get("rejected", False),
            "parsed_mail": parsed,
        }
