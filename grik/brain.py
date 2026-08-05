"""
Grik's brain — powered by the Claude Agent SDK / Claude Code CLI.

Routes through the local `claude` CLI, which authenticates via your Claude
subscription (Pro / Max) and its rolling 5-hour usage bucket, so Grik costs
nothing beyond your existing subscription instead of paid API credits.

The tool-use loop keeps the same shape as before: Grik decides which
specialist agent should do the work, delegates to it, then speaks a short
answer. The four tools (list_capabilities, delegate, provision_agent,
automate) are exposed as an in-process MCP server so Claude Code can call
them the same way it would call any built-in tool.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import threading
from pathlib import Path
from typing import Annotated

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    TextBlock,
    create_sdk_mcp_server,
    tool,
)

from .config import config
from .manager import AgentManager
from .personality import system_prompt

log = logging.getLogger("grik.brain")


def _pick_claude_cli() -> str | None:
    """
    Prefer the system-installed `claude` (authed via `claude login` → subscription)
    over the SDK-bundled binary (unauthed, falls back to API key).
    """
    return shutil.which("claude")


def _memory_path() -> Path:
    return Path(os.path.expanduser(config.memory_path))


def _read_memory() -> str:
    p = _memory_path()
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


def _write_memory(content: str) -> None:
    p = _memory_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _build_tools(manager: AgentManager):
    """Return four @tool-decorated coroutines bound to this manager instance."""

    @tool(
        "list_capabilities",
        "List the specialist agents/capabilities Grik can currently delegate to.",
        {},
    )
    async def list_capabilities(args):
        return {"content": [{"type": "text", "text": manager.capabilities_summary()}]}

    @tool(
        "delegate",
        "Hand a single, clearly-scoped sub-task to a specialist agent that runs "
        "in its own Docker container. Use this for anything involving a service "
        "(Radarr/Sonarr/etc.), the web, or any real action. Call it multiple times "
        "to fan work out across agents.",
        {
            "capability": Annotated[str, "Capability slug, e.g. 'media', 'web'."],
            "instruction": Annotated[str, "Plain-language task for that agent."],
        },
    )
    async def delegate(args):
        result = manager.delegate(args["capability"], args["instruction"])
        return {"content": [{"type": "text", "text": result}]}

    @tool(
        "provision_agent",
        "Create a NEW specialist agent when no existing capability fits the task. "
        "Spins up a fresh Docker container from the generic base-agent image, "
        "configured with the role you describe. After provisioning, delegate to it.",
        {
            "capability": Annotated[str, "Short new slug, e.g. 'home', 'finance'."],
            "role_prompt": Annotated[
                str, "System prompt describing what this agent specialises in."
            ],
        },
    )
    async def provision_agent(args):
        result = manager.provision_agent(args["capability"], args["role_prompt"])
        return {"content": [{"type": "text", "text": result}]}

    @tool(
        "read_memory",
        "Read your persistent memory about the user. Contains facts, preferences, "
        "and context you've chosen to remember across conversations. The current "
        "contents are already included in your system prompt on startup, so only "
        "call this if you want the very latest state after an update this turn.",
        {},
    )
    async def read_memory(args):
        return {"content": [{"type": "text", "text": _read_memory() or "(empty)"}]}

    @tool(
        "update_memory",
        "Replace your persistent memory file with new content. Use this to save "
        "facts about the user (name, preferences, ongoing projects, recurring tasks) "
        "that will help you in future conversations. The file persists across "
        "restarts. Keep it concise — this is a scratchpad of what matters, not a "
        "transcript. When updating, preserve prior facts unless they're contradicted; "
        "read the existing memory first (it's in your system prompt) so you don't "
        "wipe useful context. Use markdown for structure.",
        {
            "new_content": Annotated[
                str,
                "The full new contents of the memory file. This REPLACES the file — "
                "include everything you want kept, not just the new addition.",
            ],
        },
    )
    async def update_memory(args):
        _write_memory(args["new_content"])
        log.info("memory updated (%d bytes)", len(args["new_content"]))
        return {"content": [{"type": "text", "text": "Memory saved."}]}

    @tool(
        "automate",
        "Create or extend an n8n workflow to automate a recurring or triggerable "
        "task. Delegates to the n8n agent, which will search for similar existing "
        "workflows and build off them when possible, or build a new one from "
        "templates. Use this when the user wants something to happen automatically "
        "(on a schedule, on a trigger, or as a reusable automation) rather than "
        "as a one-shot action.",
        {
            "task_description": Annotated[
                str,
                "Plain-language description of what the automation should do, "
                "including triggers (schedule, webhook, event), actions, and any "
                "conditions.",
            ],
        },
    )
    async def automate(args):
        instruction = (
            f"AUTO-PROVISION WORKFLOW: {args['task_description']}\n\n"
            "Search for similar existing workflows first. If one is close enough, "
            "duplicate and modify it. Otherwise build a new one from node templates."
        )
        result = manager.delegate("n8n", instruction)
        return {"content": [{"type": "text", "text": result}]}

    return [list_capabilities, delegate, provision_agent, automate, read_memory, update_memory]


class Grik:
    """
    Sync facade around an async ClaudeSDKClient.

    A background asyncio loop hosts one long-lived client; ask() marshals each
    turn onto that loop so the existing sync callers (voice loop, web WebSocket
    handler, text-mode REPL) don't need to change.
    """

    def __init__(self, manager: AgentManager | None = None):
        self.manager = manager or AgentManager()

        # ANTHROPIC_API_KEY takes precedence over the CLI's OAuth login. It was
        # already captured into config.anthropic_api_key at import time and is
        # still passed to specialist Docker agents explicitly, so removing it
        # from this process's env only affects the CLI subprocess.
        os.environ.pop("ANTHROPIC_API_KEY", None)

        tools = _build_tools(self.manager)
        server = create_sdk_mcp_server(name="grik", tools=tools)

        sys_prompt = system_prompt(self.manager.capabilities_summary())
        memory = _read_memory().strip()
        if memory:
            sys_prompt += (
                "\n\n## What you already know about the user (persistent memory)\n"
                f"{memory}\n\n"
                "Use `update_memory` to save new facts worth remembering next time."
            )
            log.info("loaded memory from %s (%d bytes)", _memory_path(), len(memory))
        else:
            sys_prompt += (
                "\n\n## Persistent memory\n"
                "Your memory file is empty. As you learn things about the user "
                "worth remembering across conversations, save them with `update_memory`."
            )

        options = ClaudeAgentOptions(
            system_prompt=sys_prompt,
            model=config.brain_model,
            mcp_servers={"grik": server},
            allowed_tools=[f"mcp__grik__{t.name}" for t in tools],
            cli_path=_pick_claude_cli(),
        )

        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._loop.run_forever, daemon=True, name="grik-brain-loop"
        )
        self._loop_thread.start()

        self._client = ClaudeSDKClient(options=options)
        asyncio.run_coroutine_threadsafe(
            self._client.connect(), self._loop
        ).result()
        log.info("brain ready (model=%s, via Claude Code subscription)", config.brain_model)

    def ask(self, user_text: str) -> str:
        """One full turn: user text in, Grik's spoken reply out."""
        return asyncio.run_coroutine_threadsafe(
            self._ask_async(user_text), self._loop
        ).result()

    async def _ask_async(self, user_text: str) -> str:
        await self._client.query(user_text)
        parts: list[str] = []
        async for message in self._client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        parts.append(block.text)
        return "".join(parts).strip()
