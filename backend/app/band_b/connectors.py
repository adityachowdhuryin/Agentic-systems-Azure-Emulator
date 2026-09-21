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
