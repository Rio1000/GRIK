"""
Base agent — the blank specialist.

When Wullie meets a task with no matching agent, the manager launches THIS image
in a new container, configured with a role prompt supplied at provision time
(env AGENT_ROLE_PROMPT). That's how Wullie grows a new specialist for a specific
job without shipping new code.

It ships with one broad, general-purpose tool — an authenticated HTTP client —
which is enough to talk to most REST services. Give a provisioned agent narrower
powers by writing a precise role prompt.
"""
import os
import httpx

from agentlib import Tool, make_agent_app

AGENT_NAME = os.getenv("AGENT_NAME", "generic")
ROLE = os.getenv("AGENT_ROLE_PROMPT") or (
    "You are a general-purpose Wullie agent. Complete the instruction using your "
    "http_request tool where an external service is involved, and answer concisely."
)

ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH"}


def http_request(method: str, url: str, headers: dict = None, json_body: dict = None) -> str:
    """Make an HTTP request to a REST API and return the response body (truncated)."""
    method = method.upper()
    if method not in ALLOWED_METHODS:
        return f"Method {method} not allowed."
    r = httpx.request(method, url, headers=headers or {}, json=json_body, timeout=30)
    return f"{r.status_code}\n{r.text[:4000]}"


TOOLS = [
    Tool(http_request, {"name": "http_request", "description": http_request.__doc__,
         "input_schema": {"type": "object", "properties": {
             "method": {"type": "string"},
             "url": {"type": "string"},
             "headers": {"type": "object"},
             "json_body": {"type": "object"},
         }, "required": ["method", "url"]}}),
]

app = make_agent_app(AGENT_NAME, ROLE, TOOLS)
