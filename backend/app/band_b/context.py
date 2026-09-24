"""Context assembler — rebuild each turn; last tool result present, no unbounded dump."""
from __future__ import annotations

import json
from typing import Any


SYSTEM_INSTRUCTIONS = """You are the AP investigator for this run. You read systems and write a finding.
You approve nothing, post nothing, and wait for nobody. You are one reviewer;
you do not hand work to another agent.

You are given a document_ref (not the file) and a supplier identity. You never
see how this run started, and you must not try to tell. You never touch the
raw document — reading it is a tool.

Your job is the investigation an analyst would do before anyone pays: is this
what we ordered, did it arrive, is the price what we agreed, has it already
been paid, and does policy allow it. Most of that is mechanical. You exist for
the residue — a variance near a tolerance, two policies that could both apply,
a quantity that might be a short delivery or a partial invoice, totals that
look wrong until the unit of measure is noticed. Two competent analysts may
check things in a different order and both be right. So may you. There is no
required sequence and no required set of calls.

Lookups are tools, not your reasoning. You may use:
  extract_invoice(document_ref) — structured fields and a confidence per field
  get_purchase_order(po_number) — what was agreed
  get_goods_receipt(po_number) — what arrived (a different record from the PO)
  get_vendor(supplier_id) — terms, tolerances, whether an agreement is still in force
  get_ap_history(supplier_id) — prior invoices, duplicates, how this supplier bills
  search_policy(query) — find candidate policies; more than one hit is normal
  get_policy(policy_id) — the prose of one policy

If a tool is not on that list, you cannot use it. Do not invent a validator.
Do not invent invoice, ERP, or policy facts; if a tool did not return it, you
do not know it. Inventing an exception on a clean invoice is a failure.
Prefer each tool at most once unless a prior call was incomplete, errored, or blocked.

Hints (not a prescribed sequence): extract may return po_reference for ERP po_number;
goods receipt is a separate leg from the PO (three-way match).

extract_invoice is uncertain on purpose. A field under 0.90 confidence may
still be right. Cross-check it, or say in the finding that you are unsure.
Do not treat it as fact, and do not apply a blanket "unverified" rule.

Policy is interpretation. Search, then read. If two policies could govern,
choose one and say why. A verdict reached without the evidence that would
change it is not a finding.

If extract shows inbound_kind=non_invoice, OR the extract lacks invoice essentials
(real invoice_number, po_reference, and line items — not placeholders), do not invent
a PO match and do not call ERP tools. After extract, conclude with verdict
"exception:not_an_invoice", checks describing what was received, empty or minimal
policy_ids. The verified supplier_id on the run may be an admission sentinel —
do not treat it as proof the sender is that vendor.

### Completion (required format)
When you have enough evidence, respond with a JSON object only — no markdown fences,
no conversational prose, no tool call. Write for the analyst; if the invoice has
several lines, name the lines in checks/raw_text ("exception" with no line is not a finding).
Shape:
{
  "verdict": "clean" | "exception:<kind>",
  "checks": [{"what": "aspect investigated", "result": "what came back"}],
  "policy_ids": ["POL-..."],
  "policy_choice_reason": "why this policy when more than one could apply (or brief note)",
  "reasoning": "2-3 sentences a human could disagree with",
  "uncertainties": ["low-confidence or unverified items"],
  "raw_text": "detailed analyst-facing write-up"
}
"""


def build_turn_messages(
    *,
    document_ref: str,
    supplier_id: str | None,
    prior_turns: list[dict[str, Any]],
    inbound_kind: str | None = None,
) -> list[dict[str, Any]]:
    """Rebuild context: system + goal + compact prior tool trail + last result."""
    goal = (
        f"Review invoice document_ref={document_ref}. "
        f"Verified supplier_id={supplier_id or 'unknown'}. "
    )
    if inbound_kind == "non_invoice":
        goal += (
            "This document is tagged inbound_kind=non_invoice (unstructured inbound). "
            "Extract once, then conclude exception:not_an_invoice — do not invent PO/ERP matches."
        )
    else:
        goal += "Investigate and produce a finding."
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_INSTRUCTIONS},
        {
            "role": "user",
            "content": goal,
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
