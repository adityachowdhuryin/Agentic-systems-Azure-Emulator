import html
import json
import re

from app.repositories.base import EventRepository, LeadRepository, RunRepository
from app.timeutils import to_utc_iso


def _decode_mail_field(value: str | None) -> str:
    """Unescape entities and strip HTML so Zoho HTML bodies read as plain text."""
    if not value:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = re.sub(r"(?i)</div\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def get_inbound_mail_for_run(db, run_id: str) -> dict | None:
    run = RunRepository(db).get_by_run_id(run_id)
    if not run:
        return None

    inbound = EventRepository(db).get_by_event_id(run.inbound_event_id)
    if not inbound:
        return None

    try:
        stored = json.loads(inbound.payload_json)
    except json.JSONDecodeError:
        stored = {}

    inner = stored.get("payload") if isinstance(stored.get("payload"), dict) else {}

    mail_from = _decode_mail_field(
        inner.get("mail_from_live") or inner.get("mail_from") or inner.get("email") or ""
    )
    mail_to = _decode_mail_field(inner.get("mail_to") or "")
    mail_subject = _decode_mail_field(inner.get("mail_subject") or "")
    mail_body = _decode_mail_field(inner.get("mail_body") or "")
    mail_message_id = (
        inner.get("mail_message_id") or stored.get("event_id") or inbound.event_id
    )

    # Older mail runs may only have partial fields — fall back to lead data
    if not mail_body or not mail_from:
        lead = LeadRepository(db).get_by_lead_id(run.lead_id)
        if lead:
            if not mail_from:
                mail_from = _decode_mail_field(lead.email or "")
            if not mail_body and lead.source == "Zoho Mail":
                mail_body = _decode_mail_field(lead.requirement or "")

    if not any([mail_from, mail_to, mail_subject, mail_body]):
        return None

    invoice_content = inner.get("invoice_content") or ""
    if isinstance(invoice_content, dict):
        invoice_content = json.dumps(invoice_content, indent=2)
    else:
        invoice_content = str(invoice_content or "")
    invoice_source = str(inner.get("invoice_source") or "")
    attachment_filename = str(inner.get("attachment_filename") or "")
    if not attachment_filename and invoice_source.startswith("attachment:"):
        attachment_filename = invoice_source.split(":", 1)[1].strip()

    return {
        "run_id": run.run_id,
        "lead_id": run.lead_id,
        "source": inbound.source,
        "event_id": inbound.event_id,
        "mail_from": mail_from,
        "mail_to": mail_to,
        "mail_subject": mail_subject,
        "mail_body": mail_body,
        "mail_message_id": mail_message_id,
        "received_at": to_utc_iso(inbound.received_at) if inbound.received_at else None,
        "attachment_filename": attachment_filename,
        "invoice_content": invoice_content,
        "invoice_source": invoice_source,
    }
