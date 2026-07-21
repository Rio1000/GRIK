"""
agentlib — the shared runtime every Grik agent is built on.

An agent is: a name, a system prompt, and a set of Python tool functions.
This module turns those into a FastAPI service exposing:
    GET  /health   -> {"ok": true}
    POST /execute  -> {"instruction": str, "context": dict} -> {"result": str}

Inside /execute we run a small Anthropic tool-use loop so the agent can
interpret plain-language instructions and call its own tools. Agents are
deliberately narrow: each one only knows how to do its own job.
"""
from __future__ import annotations

import os
import inspect
from typing import Callable

from anthropic import Anthropic
from fastapi import FastAPI
from pydantic import BaseModel

_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
_MODEL = os.getenv("GRIK_BRAIN_MODEL", "claude-sonnet-4-6")


class Tool:
    def __init__(self, fn: Callable, schema: dict):
        self.fn = fn
        self.name = schema["name"]
        self.schema = schema


class Task(BaseModel):
    instruction: str
    context: dict = {}


def make_agent_app(name: str, system_prompt: str, tools: list[Tool]) -> FastAPI:
    app = FastAPI(title=f"grik-agent-{name}")
    by_name = {t.name: t for t in tools}
    schemas = [t.schema for t in tools]

    @app.get("/health")
    def health():
        return {"ok": True, "agent": name}

    @app.post("/execute")
    def execute(task: Task):
        messages = [{"role": "user", "content": _frame(task)}]
        for _ in range(8):  # bounded tool loop
            resp = _client.messages.create(
                model=_MODEL, max_tokens=1024,
                system=system_prompt, tools=schemas, messages=messages,
            )
            messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason != "tool_use":
                return {"result": "".join(b.text for b in resp.content if b.type == "text").strip()}
            results = []
            for b in resp.content:
                if b.type == "tool_use":
                    tool = by_name.get(b.name)
                    try:
                        out = tool.fn(**b.input) if tool else f"unknown tool {b.name}"
                    except Exception as e:
                        out = f"tool error: {e}"
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": str(out)})
            messages.append({"role": "user", "content": results})
        return {"result": "Stopped after too many steps without a final answer."}

    return app


def _frame(task: Task) -> str:
    ctx = f"\n\nContext: {task.context}" if task.context else ""
    return f"{task.instruction}{ctx}"
