"""Hard allowlist — tools not listed are structurally unreachable."""
from __future__ import annotations

ALLOWED_TOOLS = frozenset(
    {
        "extract_invoice",
        "get_purchase_order",
        "get_goods_receipt",
        "get_vendor",
        "get_ap_history",
        "search_policy",
        "get_policy",
    }
)

TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "extract_invoice",
        "description": "Extract structured invoice fields + per-field confidence from document_ref",
        "parameters": {
            "type": "object",
            "properties": {"document_ref": {"type": "string"}},
            "required": ["document_ref"],
        },
    },
    {
        "type": "function",
        "name": "get_purchase_order",
        "description": "Fetch purchase order by po_number from ERP",
        "parameters": {
            "type": "object",
            "properties": {"po_number": {"type": "string"}},
            "required": ["po_number"],
        },
    },
    {
        "type": "function",
        "name": "get_goods_receipt",
        "description": "Fetch goods receipts for a PO (third leg of three-way match)",
        "parameters": {
            "type": "object",
            "properties": {"po_number": {"type": "string"}},
            "required": ["po_number"],
        },
    },
    {
        "type": "function",
        "name": "get_vendor",
        "description": "Fetch vendor master (terms, tolerances, hold, agreement dates)",
        "parameters": {
            "type": "object",
            "properties": {"supplier_id": {"type": "string"}},
            "required": ["supplier_id"],
        },
    },
    {
        "type": "function",
        "name": "get_ap_history",
        "description": "Fetch prior invoices / AP history for a supplier",
        "parameters": {
            "type": "object",
            "properties": {"supplier_id": {"type": "string"}},
            "required": ["supplier_id"],
        },
    },
    {
        "type": "function",
        "name": "search_policy",
        "description": "Search policy store by free-text query (may return multiple policies)",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "get_policy",
        "description": "Fetch full policy prose by policy_id",
        "parameters": {
            "type": "object",
            "properties": {"policy_id": {"type": "string"}},
            "required": ["policy_id"],
        },
    },
]


def assert_registered(tool_name: str) -> None:
    if tool_name not in ALLOWED_TOOLS:
        raise PermissionError(f"Unregistered tool cannot be invoked: {tool_name}")
