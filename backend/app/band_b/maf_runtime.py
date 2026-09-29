"""Microsoft Agent Framework adapter for Band B (optional; falls back to Responses API).

Preserves broker, policy gate, journal, and tool registry. Set AGENT_RUNTIME=maf to use
Agent Framework when installed; default remains responses (hand-rolled Foundry loop).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable

logger = logging.getLogger(__name__)


def maf_available() -> bool:
    try:
        import agent_framework  # noqa: F401

        return True
    except ImportError:
        return False


def use_maf() -> bool:
    runtime = (os.getenv("AGENT_RUNTIME") or "").lower()
    if runtime in {"maf", "agent-framework", "agent_framework"}:
        return maf_available()
    if runtime in {"responses", "handrolled", "legacy"}:
        return False
    # Default: prefer MAF when installed
    return maf_available()


def build_maf_tools(execute_tool: Callable[[str, dict], Any]) -> list:
    """Wrap registry tools as Agent Framework callables with policy enforced outside."""
    from app.band_b.registry import TOOL_SCHEMAS

    tools = []
    for schema in TOOL_SCHEMAS:
        name = schema["name"]

        def _make(n: str):
            def _fn(**kwargs):
                return execute_tool(n, kwargs)

            _fn.__name__ = n
            _fn.__doc__ = schema.get("description") or n
            return _fn

        tools.append(_make(name))
    return tools


async def run_maf_turn(
    *,
    instructions: str,
    user_message: str,
    tools: list,
) -> str:
    """One-shot Agent Framework run; returns assistant text."""
    from azure.identity import DefaultAzureCredential
    from agent_framework import Agent

    try:
        from agent_framework.foundry import FoundryChatClient
    except ImportError:
        from agent_framework.azure import AzureAIAgentClient as FoundryChatClient  # type: ignore

    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT") or ""
    model = os.getenv("FOUNDRY_MODEL_NAME") or "gpt-5-mini"
    credential = DefaultAzureCredential()
    try:
        client = FoundryChatClient(
            project_endpoint=endpoint,
            model=model,
            credential=credential,
        )
    except TypeError:
        client = FoundryChatClient(credential=credential)  # env-based

    agent = Agent(
        client=client,
        name="InvoiceReviewAgent",
        instructions=instructions,
        tools=tools,
    )
    result = await agent.run(user_message)
    text = getattr(result, "text", None) or str(result)
    return text
