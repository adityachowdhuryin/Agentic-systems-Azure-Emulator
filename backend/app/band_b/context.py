"""Context assembler — rebuild each turn; last tool result present, no unbounded dump."""
from __future__ import annotations

import json
from typing import Any


SYSTEM_INSTRUCTIONS = """You are an AP invoice review agent (read-only).
Goal: investigate the supplier invoice and produce a finding for an AP analyst.

You have exactly these tools: extract_invoice, get_purchase_order, get_goods_receipt,
get_vendor, get_ap_history, search_policy, get_policy.
Decide your own next step. Do not assume a fixed checklist order.

Rules:
- Start by extracting the invoice via document_ref when you have not yet.
- Extraction may return po_reference (or similar); pass that value as po_number to ERP tools.
- Use goods receipt separately from the PO (three-way match).
- Search policy then fetch by id; if two policies could apply, choose one and say why.
- If extract_invoice returns field_confidence below 0.90, cross-check or state uncertainty.
- Never invent ERP facts — call tools.
- Prefer calling each tool at most once unless a result was incomplete or blocked.
- When done, respond with a JSON object only (no tools), shape:
  {
    "verdict": "clean" | "exception:<kind>",
    "checks": [{"what": "...", "result": "..."}],
    "policy_ids": ["POL-..."],
    "policy_choice_reason": "...",
    "reasoning": "2-3 sentences",
    "uncertainties": ["..."],
    "raw_text": "analyst-facing write-up"
  }
You cannot change any system. You only read and explain.
"""


def build_turn_messages(
    *,
    document_ref: str,
    supplier_id: str | None,
    prior_turns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Rebuild context: system + goal + compact prior tool trail + last result."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_INSTRUCTIONS},
        {
            "role": "user",
            "content": (
                f"Review invoice document_ref={document_ref}. "
                f"Verified supplier_id={supplier_id or 'unknown'}. "
                "Investigate and produce a finding."
            ),
        },
    ]
    # Keep only last 6 tool exchanges to avoid stale pile-up
    for turn in prior_turns[-6:]:
        if turn.get("tool_name"):
            messages.append(
                {
                    "role": "assistant",
                    "content": f"Decided: {turn.get('decided')} → call {turn['tool_name']}",
                }
            )
            result = turn.get("tool_result") or {}
            # Truncate large payloads
            blob = json.dumps(result)
            if len(blob) > 4000:
                blob = blob[:4000] + "...(truncated)"
            messages.append(
                {
                    "role": "user",
                    "content": f"Tool {turn['tool_name']} returned: {blob}",
                }
            )
        elif turn.get("decided"):
            messages.append({"role": "assistant", "content": turn["decided"]})
    return messages
