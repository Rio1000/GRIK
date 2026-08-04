"""
Grik's brain.

An Anthropic tool-use loop. Grik doesn't do the work itself — it decides
which specialist agent should, delegates, and then speaks a short answer.
"""
from __future__ import annotations

import json
import logging

from anthropic import Anthropic

from .config import config
from .personality import system_prompt
from .manager import AgentManager

log = logging.getLogger("grik.brain")

TOOLS = [
    {
        "name": "list_capabilities",
        "description": "List the specialist agents/capabilities Grik can currently delegate to.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "delegate",
        "description": (
            "Hand a single, clearly-scoped sub-task to a specialist agent that runs "
            "in its own Docker container. Use this for anything involving a service "
            "(Radarr/Sonarr/etc.), the web, or any real action. Call it multiple times "
            "to fan work out across agents."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "capability": {"type": "string", "description": "Capability slug, e.g. 'media', 'web'."},
                "instruction": {"type": "string", "description": "Plain-language task for that agent."},
            },
            "required": ["capability", "instruction"],
        },
    },
    {
        "name": "provision_agent",
        "description": (
            "Create a NEW specialist agent when no existing capability fits the task. "
            "Spins up a fresh Docker container from the generic base-agent image, "
            "configured with the role you describe. After provisioning, delegate to it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "capability": {"type": "string", "description": "Short new slug, e.g. 'home', 'finance'."},
                "role_prompt": {"type": "string", "description": "System prompt describing what this agent specialises in."},
            },
            "required": ["capability", "role_prompt"],
        },
    },
    {
        "name": "automate",
        "description": (
            "Create or extend an n8n workflow to automate a recurring or triggerable "
            "task. Delegates to the n8n agent, which will search for similar existing "
            "workflows and build off them when possible, or build a new one from "
            "templates. Use this when the user wants something to happen automatically "
            "(on a schedule, on a trigger, or as a reusable automation) rather than "
            "as a one-shot action."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_description": {
                    "type": "string",
                    "description": (
                        "Plain-language description of what the automation should do, "
                        "including triggers (schedule, webhook, event), actions, and "
                        "any conditions."
                    ),
                },
            },
            "required": ["task_description"],
        },
    },
]


class Grik:
    def __init__(self, manager: AgentManager | None = None):
        self.client = Anthropic(api_key=config.anthropic_api_key)
        self.manager = manager or AgentManager()
        self.history: list[dict] = []

    def _run_tool(self, name: str, args: dict) -> str:
        log.info("tool %s %s", name, args)
        if name == "list_capabilities":
            return self.manager.capabilities_summary()
        if name == "delegate":
            return self.manager.delegate(args["capability"], args["instruction"])
        if name == "provision_agent":
            return self.manager.provision_agent(args["capability"], args["role_prompt"])
        if name == "automate":
            instruction = (
                f"AUTO-PROVISION WORKFLOW: {args['task_description']}\n\n"
                "Search for similar existing workflows first. If one is close enough, "
                "duplicate and modify it. Otherwise build a new one from node templates."
            )
            return self.manager.delegate("n8n", instruction)
        return f"Unknown tool: {name}"

    def ask(self, user_text: str) -> str:
        """One full turn: user text in, Grik's spoken reply out."""
        self.history.append({"role": "user", "content": user_text})
        sys = system_prompt(self.manager.capabilities_summary())

        while True:
            resp = self.client.messages.create(
                model=config.brain_model,
                max_tokens=1024,
                system=sys,
                tools=TOOLS,
                messages=self.history,
            )
            self.history.append({"role": "assistant", "content": resp.content})

            if resp.stop_reason != "tool_use":
                # final spoken answer
                text = "".join(b.text for b in resp.content if b.type == "text").strip()
                return text

            # run every requested tool, feed results back
            results = []
            for block in resp.content:
                if block.type == "tool_use":
                    out = self._run_tool(block.name, block.input)
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": out,
                    })
            self.history.append({"role": "user", "content": results})
