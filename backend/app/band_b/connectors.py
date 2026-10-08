"""HTTP connectors to local mock systems (port 8090)."""
from __future__ import annotations

import httpx

from app.config import settings


class MockConnectors:
    def __init__(self, base_url: str | None = None):
        self.base = (base_url or settings.mock_systems_url).rstrip("/")

    def call(self, tool_name: str, args: dict, credential: str) -> dict:
        headers = {"x-credential": credential}
        with httpx.Client(timeout=30.0) as client:
            if tool_name == "extract_invoice":
                doc_ref = args["document_ref"]
                # Live Teams/Zoho uploads live in blob/SQL — never depend on mocks disk
                # or mocks HMAC for extract (ERP/policy still go through mocks + broker).
                if str(doc_ref).startswith("live-"):
                    return self._extract_from_document_store(doc_ref)
                r = client.get(
                    f"{self.base}/extraction/invoice",
                    params={"document_ref": doc_ref},
                    headers=headers,
                )
                if r.status_code in (401, 404):
                    fallback = self._extract_from_document_store(doc_ref)
                    if "error" not in fallback:
                        return fallback
                    if r.status_code == 404:
                        return fallback
            elif tool_name == "get_purchase_order":
                r = client.get(
                    f"{self.base}/erp/purchase-orders/{args['po_number']}",
                    headers=headers,
                )
            elif tool_name == "get_goods_receipt":
                r = client.get(
                    f"{self.base}/erp/goods-receipts",
                    params={"po_number": args["po_number"]},
                    headers=headers,
                )
            elif tool_name == "get_vendor":
                r = client.get(
                    f"{self.base}/erp/vendors/{args['supplier_id']}",
                    headers=headers,
                )
            elif tool_name == "get_ap_history":
                r = client.get(
                    f"{self.base}/erp/ap-history/{args['supplier_id']}",
                    headers=headers,
                )
            elif tool_name == "search_policy":
                r = client.get(
                    f"{self.base}/policy/search",
                    params={"q": args["query"]},
                    headers=headers,
                )
            elif tool_name == "get_policy":
                r = client.get(
                    f"{self.base}/policy/{args['policy_id']}",
                    headers=headers,
                )
            else:
                raise PermissionError(f"No connector for {tool_name}")
            if r.status_code >= 400:
                return {"error": r.status_code, "detail": r.text}
            return r.json()

    @staticmethod
    def _invoice_from_payload(raw: dict) -> dict | None:
        import json

        inner = raw.get("payload") if isinstance(raw.get("payload"), dict) else raw
        content = inner.get("invoice_content") if isinstance(inner, dict) else None
        if isinstance(content, str) and content.strip():
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                return None
            return parsed if isinstance(parsed, dict) else None
        if isinstance(content, dict):
            return content
        live = raw.get("live_invoice")
        return live if isinstance(live, dict) else None

    @classmethod
    def _load_invoice_from_inbound_event(cls, document_ref: str) -> dict | None:
        """Fallback when blob/local file missing — invoice JSON is in SQL inbound payload."""
        import json

        from app.database import InboundEvent, Run, SessionLocal

        db = SessionLocal()
        try:
            run = (
                db.query(Run)
                .filter(Run.document_ref == document_ref)
                .order_by(Run.id.desc())
                .first()
            )
            if run and run.inbound_event_id:
                evt = (
                    db.query(InboundEvent)
                    .filter(InboundEvent.event_id == run.inbound_event_id)
                    .first()
                )
                if evt and evt.payload_json:
                    try:
                        raw = json.loads(evt.payload_json)
                    except json.JSONDecodeError:
                        raw = None
                    if isinstance(raw, dict):
                        found = cls._invoice_from_payload(raw)
                        if found:
                            return found
            # Last resort: scan recent inbound rows for this document_ref
            rows = (
                db.query(InboundEvent)
                .order_by(InboundEvent.id.desc())
                .limit(40)
                .all()
            )
            for evt in rows:
                if not evt.payload_json or document_ref not in evt.payload_json:
                    continue
                try:
                    raw = json.loads(evt.payload_json)
                except json.JSONDecodeError:
                    continue
                if not isinstance(raw, dict):
                    continue
                found = cls._invoice_from_payload(raw)
                if found:
                    return found
            return None
        except Exception:
            return None
        finally:
            db.close()

    @classmethod
    def _extract_from_document_store(cls, document_ref: str) -> dict:
        from app.storage.documents import get_document_store

        inv = get_document_store().get_json(document_ref)
        if not inv:
            inv = cls._load_invoice_from_inbound_event(document_ref)
        if not inv:
            return {"error": 404, "detail": "document not found"}
        if "lines" not in inv:
            inv = {**inv, "lines": []}
        return {
            "document_ref": document_ref,
            "extracted": inv,
            "field_confidence": {
                k: 0.95
                for k in (
                    "invoice_number",
                    "supplier_id",
                    "invoice_date",
                    "po_reference",
                    "total_amount",
                )
                if inv.get(k) is not None and inv.get(k) != ""
            },
            "note": "Served from document store (live upload).",
        }
