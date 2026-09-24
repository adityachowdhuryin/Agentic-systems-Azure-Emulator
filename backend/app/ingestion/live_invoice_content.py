"""Parse live Zoho invoice content (attachment or body) and persist for extract."""
from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path
from typing import Any

# Repo root: backend/app/ingestion -> parents[3]
REPO_ROOT = Path(__file__).resolve().parents[3]
UPLOADS_DIR = REPO_ROOT / "data" / "invoice_uploads"

_INVOICE_KEYS = ("supplier_id", "invoice_number", "po_reference", "lines", "total_amount")


def uploads_dir() -> Path:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOADS_DIR


def _decode_maybe_base64(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    # Zoho sometimes returns base64 for attachment content
    if re.fullmatch(r"[A-Za-z0-9+/=\s]+", text) and len(text) > 40 and "{" not in text[:20]:
        try:
            decoded = base64.b64decode(text, validate=False).decode("utf-8", errors="replace")
            if "{" in decoded or "supplier_id" in decoded or "invoice" in decoded.lower():
                return decoded
        except Exception:
            pass
    return text


def _normalize_attachment_text(raw: Any) -> str:
    """Coerce Deluge FILE / toString / base64 / nested content into plain text."""
    if raw is None:
        return ""
    if isinstance(raw, (bytes, bytearray)):
        text = raw.decode("utf-8", errors="replace")
    elif isinstance(raw, dict):
        # Nested shapes: { content }, { data }, { text }
        nested = raw.get("content")
        if nested is None:
            nested = raw.get("data") or raw.get("text") or raw.get("body")
        if nested is not None and nested is not raw:
            return _normalize_attachment_text(nested)
        text = json.dumps(raw)
    else:
        text = str(raw)
    text = text.strip()
    # Deluge FILE toString sometimes prefixes metadata before JSON
    if "supplier_id" not in text and "{" in text:
        # still try base64 / parse on full string
        pass
    return _decode_maybe_base64(text)


def _looks_like_invoice(data: dict[str, Any]) -> bool:
    if not isinstance(data, dict):
        return False
    supplier = str(data.get("supplier_id") or "").strip()
    if not supplier:
        return False
    if data.get("invoice_number") or data.get("po_reference"):
        return True
    lines = data.get("lines")
    return isinstance(lines, list) and len(lines) > 0


def _parse_json_blob(text: str) -> dict[str, Any] | None:
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    # Body may wrap JSON in prose — try full parse first, then first {...} block
    candidates = [cleaned]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        candidates.append(cleaned[start : end + 1])
    for cand in candidates:
        try:
            data = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if _looks_like_invoice(data):
            return data
    return None


def _parse_text_kv(text: str) -> dict[str, Any] | None:
    """Light key: value parser for paste of pack-like fields."""
    if not text or not text.strip():
        return None
    fields: dict[str, Any] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip().lower().replace(" ", "_")
        val = val.strip().strip('"').strip("'")
        if key in ("supplier_id", "invoice_number", "po_reference", "po_number", "currency", "supplier_name", "invoice_date"):
            if key == "po_number":
                key = "po_reference"
            fields[key] = val
        elif key == "total_amount":
            try:
                fields[key] = float(val.replace(",", ""))
            except ValueError:
                fields[key] = val
    if _looks_like_invoice(fields):
        fields.setdefault("lines", [])
        return fields
    return None


def normalize_invoice_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Ensure pack-shaped keys for extract / ERP match."""
    out = dict(data)
    if "po_number" in out and not out.get("po_reference"):
        out["po_reference"] = out["po_number"]
    out["supplier_id"] = str(out.get("supplier_id") or "").strip()
    if "lines" not in out or not isinstance(out["lines"], list):
        out["lines"] = out.get("lines") or []
    return out


def parse_invoice_text(text: str) -> dict[str, Any] | None:
    decoded = _normalize_attachment_text(text)
    data = _parse_json_blob(decoded)
    if data:
        return normalize_invoice_dict(data)
    data = _parse_text_kv(decoded)
    if data:
        return normalize_invoice_dict(data)
    return None


def _attachment_filename(att: Any) -> str:
    if not isinstance(att, dict):
        return ""
    return str(att.get("filename") or att.get("fileName") or att.get("name") or "").strip()


def _attachment_content(att: Any) -> str:
    if not isinstance(att, dict):
        return ""
    raw = att.get("content")
    if raw is None:
        raw = att.get("body") or att.get("data") or att.get("fileContent")
    if raw is None and att.get("contentBase64"):
        try:
            raw = base64.b64decode(str(att["contentBase64"]), validate=False).decode(
                "utf-8", errors="replace"
            )
        except Exception:
            raw = ""
    if raw is None:
        raw = ""
    return _normalize_attachment_text(raw)


def extract_live_invoice(
    *,
    attachments: list[Any] | None,
    body: str,
) -> tuple[dict[str, Any], str] | None:
    """
    Prefer .json/.txt attachment content; else body paste.
    Returns (invoice_dict, source_label) or None.
    """
    for att in attachments or []:
        name = _attachment_filename(att).lower()
        if name and not (name.endswith(".json") or name.endswith(".txt")):
            continue
        content = _attachment_content(att)
        if not content.strip():
            continue
        # If no extension but content parses, still accept
        if name and not (name.endswith(".json") or name.endswith(".txt")):
            continue
        if not name:
            # unnamed — only if it parses as invoice
            pass
        inv = parse_invoice_text(content)
        if inv:
            label = _attachment_filename(att) or "attachment"
            return inv, f"attachment:{label}"

    # Also try any attachment whose content parses even without .json/.txt
    for att in attachments or []:
        name = _attachment_filename(att).lower()
        if name.endswith(".json") or name.endswith(".txt") or not name:
            continue  # already tried json/txt; skip binaries
        # skip non text-like

    inv = parse_invoice_text(body or "")
    if inv:
        return inv, "body"
    return None


def make_document_ref(*, message_id: str, source_label: str, invoice: dict[str, Any]) -> str:
    """Short stable id so mocks/filesystem never truncate mid-name."""
    inv_no = re.sub(r"[^a-zA-Z0-9_-]", "-", str(invoice.get("invoice_number") or "inv"))[:20]
    mid = re.sub(r"[^a-zA-Z0-9]", "", (message_id or ""))[-10:] or "nomsg"
    digest = hashlib.sha1(
        json.dumps(invoice, sort_keys=True, default=str).encode()
        + mid.encode()
        + (source_label or "").encode()
    ).hexdigest()[:10]
    kind = "att" if (source_label or "").startswith("attachment") else "body"
    return f"live-{inv_no}-{digest}-{kind}-{mid}"[:80]


def build_non_invoice_document(
    *,
    raw_text: str,
    attachment_filename: str = "",
    subject: str = "",
) -> dict[str, Any]:
    """Stored extract payload for unrelated live inbound (agent should reject)."""
    text = (raw_text or "").strip() or "(empty message)"
    return {
        "inbound_kind": "non_invoice",
        "invoice_number": "NONINV",
        "raw_text": text[:8000],
        "attachment_filename": attachment_filename or "",
        "mail_subject": subject or "",
        "note": "Unstructured inbound; not a pack-shaped supplier invoice",
        "lines": [],
    }


def resolve_non_invoice_from_mail(
    raw: dict[str, Any],
    *,
    body: str,
    message_id: str,
    subject: str = "",
) -> tuple[dict[str, Any], str, str]:
    """Always succeeds: attachment text preferred, else body."""
    attachments = coerce_attachments(raw.get("attachments"))
    for att in attachments:
        name = _attachment_filename(att)
        content = _attachment_content(att).strip()
        if not name and not content:
            continue
        # Skip if this attachment already parsed as a real invoice (caller should check first)
        doc = build_non_invoice_document(
            raw_text=content or f"(empty attachment {name or 'file'})",
            attachment_filename=name,
            subject=subject,
        )
        source = f"attachment:{name}" if name else "attachment"
        document_ref = make_document_ref(
            message_id=message_id, source_label=source, invoice=doc
        )
        store_invoice_upload(document_ref, doc)
        return doc, document_ref, source

    doc = build_non_invoice_document(raw_text=body or "", subject=subject)
    document_ref = make_document_ref(
        message_id=message_id, source_label="body", invoice=doc
    )
    store_invoice_upload(document_ref, doc)
    return doc, document_ref, "body"


def resolve_non_invoice_from_teams(
    *,
    text: str,
    activity_id: str,
) -> tuple[dict[str, Any], str, str]:
    doc = build_non_invoice_document(raw_text=text or "", subject="Teams message")
    document_ref = make_document_ref(
        message_id=activity_id or "teams", source_label="body", invoice=doc
    )
    store_invoice_upload(document_ref, doc)
    return doc, document_ref, "body"


def resolve_live_invoice_from_teams(
    *,
    text: str,
    activity_id: str,
) -> tuple[dict[str, Any], str, str] | None:
    """Parse pack-shaped invoice from Teams chat text (prose + JSON OK). Persist upload."""
    inv = parse_invoice_text(text or "")
    if not inv:
        return None
    source_label = "body"
    document_ref = make_document_ref(
        message_id=activity_id or "teams", source_label=source_label, invoice=inv
    )
    store_invoice_upload(document_ref, inv)
    return inv, document_ref, source_label


def store_invoice_upload(document_ref: str, invoice: dict[str, Any]) -> Path:
    path = uploads_dir() / f"{document_ref}.json"
    path.write_text(json.dumps(invoice, indent=2), encoding="utf-8")
    return path


def coerce_attachments(raw: Any) -> list[Any]:
    """Deluge sometimes sends attachments as the string '[]' or a JSON array string."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [_coerce_attachment_row(a) for a in raw]
    if isinstance(raw, str):
        text = raw.strip()
        if not text or text == "[]":
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [_coerce_attachment_row(a) for a in parsed]
        except json.JSONDecodeError:
            return []
    return []


def _coerce_attachment_row(att: Any) -> Any:
    if not isinstance(att, dict):
        return att
    out = dict(att)
    # Normalize content field in place for downstream parsers
    if "content" in out or "body" in out or "data" in out:
        out["content"] = _attachment_content(out)
    return out


def resolve_live_invoice_from_mail(
    raw: dict[str, Any],
    *,
    body: str,
    message_id: str,
) -> tuple[dict[str, Any], str, str] | None:
    """Parse + persist. Returns (invoice, document_ref, source_label) or None."""
    attachments = coerce_attachments(raw.get("attachments"))
    found = extract_live_invoice(attachments=attachments, body=body)
    if not found:
        return None
    invoice, source_label = found
    document_ref = make_document_ref(
        message_id=message_id, source_label=source_label, invoice=invoice
    )
    store_invoice_upload(document_ref, invoice)
    return invoice, document_ref, source_label
