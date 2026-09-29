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
                r = client.get(
                    f"{self.base}/extraction/invoice",
                    params={"document_ref": args["document_ref"]},
                    headers=headers,
                )
                if r.status_code == 404:
                    # Live Azure uploads live in blob/local document store, not mocks disk
                    return self._extract_from_document_store(args["document_ref"])
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
    def _extract_from_document_store(document_ref: str) -> dict:
        from app.storage.documents import get_document_store

        inv = get_document_store().get_json(document_ref)
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
