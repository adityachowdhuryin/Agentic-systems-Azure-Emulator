"""Independent policy gate — not a prompt rule (Assignment 02 T7)."""
from __future__ import annotations

from app.band_b.registry import ALLOWED_TOOLS


def check_tool_allowed(
    *,
    tool_name: str,
    tool_args: dict,
    supplier_id: str | None,
    run_supplier_id: str | None,
) -> tuple[bool, str]:
    if tool_name not in ALLOWED_TOOLS:
        return False, f"Tool {tool_name} is not in the registry"

    # Demo deny: explicit probe tool never registered — handled above.
    # Deny cross-supplier ERP lookups when args carry a different supplier_id.
    if tool_name in {"get_vendor", "get_ap_history"}:
        requested = tool_args.get("supplier_id")
        if run_supplier_id and requested and requested != run_supplier_id:
            return False, (
                f"Policy gate blocked {tool_name}: supplier {requested} "
                f"outside run scope {run_supplier_id}"
            )

    if tool_name == "get_policy" and tool_args.get("policy_id") == "POL-BLOCK-DEMO":
        return False, "Policy gate blocked get_policy(POL-BLOCK-DEMO) for demo"

    return True, "ok"
