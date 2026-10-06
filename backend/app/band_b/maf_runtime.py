"""Microsoft Agent Framework adapter for Band B (optional; falls back to Responses API).

One model turn per call: FoundryChatClient returns text and/or function_call requests.
Tool execution (policy gate, broker, journal) stays in agent_loop.py.
Set AGENT_RUNTIME=maf to use Agent Framework when installed.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


class _FunctionCallItem:
    """Minimal object compatible with agent_loop._extract_tool_calls()."""

    def __init__(self, *, name: str, arguments: str, call_id: str | None) -> None:
        self.type = "function_call"
        self.name = name
        self.arguments = arguments
        self.call_id = call_id


@dataclass
class MafModelResponse:
    """Adapter matching the shape agent_loop expects from Responses API."""

    output_text: str = ""
    output: list[_FunctionCallItem] = field(default_factory=list)


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


def _endpoint() -> str:
    from app.config import settings

    return os.getenv("FOUNDRY_PROJECT_ENDPOINT") or settings.foundry_project_endpoint


def _model_name() -> str:
    from app.config import settings

    return os.getenv("FOUNDRY_MODEL_NAME") or settings.foundry_model_name


def _messages_to_maf(messages: list[dict[str, Any]]) -> list:
    from agent_framework import Message

    out = []
    for m in messages:
        role = m.get("role") or "user"
        if role == "system":
            role = "developer"
        content = m.get("content") or ""
        if not str(content).strip():
            continue
        out.append(Message(role=role, contents=str(content)))
    return out


def _build_schema_tools() -> list:
    """Schema-only FunctionTools — execution happens in agent_loop after governance."""
    from agent_framework import FunctionTool

    from app.band_b.registry import TOOL_SCHEMAS

    tools = []
    for schema in TOOL_SCHEMAS:
        tools.append(
            FunctionTool(
                name=schema["name"],
                description=schema.get("description") or schema["name"],
                input_model=schema.get("parameters") or {"type": "object", "properties": {}},
            )
        )
    return tools


def _chat_response_to_maf(resp) -> MafModelResponse:
    output: list[_FunctionCallItem] = []
    for msg in getattr(resp, "messages", None) or []:
        for content in getattr(msg, "contents", None) or []:
            data = content.to_dict() if hasattr(content, "to_dict") else {}
            if data.get("type") != "function_call":
                continue
            args_raw = data.get("arguments") or "{}"
            if not isinstance(args_raw, str):
                args_raw = json.dumps(args_raw)
            output.append(
                _FunctionCallItem(
                    name=str(data.get("name") or ""),
                    arguments=args_raw,
                    call_id=data.get("call_id"),
                )
            )
    text = getattr(resp, "text", None) or ""
    return MafModelResponse(output_text=str(text), output=output)


def _foundry_client():
    from azure.identity import DefaultAzureCredential
    from agent_framework import FunctionInvocationConfiguration
    from agent_framework.foundry import FoundryChatClient

    endpoint = _endpoint()
    model = _model_name()
    if not endpoint:
        raise ValueError("FOUNDRY_PROJECT_ENDPOINT is required for MAF runtime")

    return FoundryChatClient(
        project_endpoint=endpoint,
        model=model,
        credential=DefaultAzureCredential(),
        function_invocation_configuration=FunctionInvocationConfiguration(enabled=False),
    )


async def _call_model_maf_async(messages: list[dict[str, Any]]) -> MafModelResponse:
    from agent_framework import ChatOptions

    client = _foundry_client()
    try:
        maf_messages = _messages_to_maf(messages)
        tools = _build_schema_tools()
        instructions = ""
        for m in messages:
            if m.get("role") == "system":
                instructions = str(m.get("content") or "")
                break

        options = ChatOptions(tools=tools, instructions=instructions or None)
        resp = await client.get_response(maf_messages, options=options)
        return _chat_response_to_maf(resp)
    finally:
        close = getattr(client, "close", None) or getattr(client, "aclose", None)
        if close is not None:
            try:
                result = close()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.debug("FoundryChatClient close failed", exc_info=True)


def _call_model_maf(messages: list[dict[str, Any]]) -> MafModelResponse:
    """Sync entry: one MAF model turn (Foundry via Agent Framework)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError(
            "_call_model_maf cannot run inside an active event loop; "
            "call _call_model_maf_async from async code"
        )

    # Fresh loop per turn — avoids "Event loop is closed" from reused httpx/AF clients
    # after asyncio.run() tears down the previous loop.
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_call_model_maf_async(messages))
    finally:
        try:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            logger.debug("MAF event-loop cleanup failed", exc_info=True)
        finally:
            asyncio.set_event_loop(None)
            loop.close()


def build_maf_tools(execute_tool: Callable[[str, dict], Any]) -> list:
    """Wrap registry tools as Agent Framework callables (for future full-agent use)."""
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
    """One-shot Agent.run (not used by agent_loop — budgets/journal need per-turn control)."""
    from azure.identity import DefaultAzureCredential
    from agent_framework import Agent

    from agent_framework.foundry import FoundryChatClient

    endpoint = _endpoint()
    model = _model_name()
    credential = DefaultAzureCredential()
    client = FoundryChatClient(
        project_endpoint=endpoint,
        model=model,
        credential=credential,
    )
    agent = Agent(
        client=client,
        name="InvoiceReviewAgent",
        instructions=instructions,
        tools=tools,
    )
    result = await agent.run(user_message)
    text = getattr(result, "text", None) or str(result)
    return text
