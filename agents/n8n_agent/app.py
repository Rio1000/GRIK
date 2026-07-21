"""
n8n agent — Grik's workflow automation specialist.

Talks to an n8n instance via its REST API (v1).
Set N8N_URL and N8N_API_KEY.
"""
import os
import json
import httpx

from agentlib import Tool, make_agent_app

N8N_URL = os.getenv("N8N_URL", "http://n8n:5678").rstrip("/")
N8N_API_KEY = os.getenv("N8N_API_KEY", "")

_HEADERS = {
    "X-N8N-API-KEY": N8N_API_KEY,
    "Content-Type": "application/json",
}


def _get(path: str, **params) -> dict | list:
    r = httpx.get(f"{N8N_URL}/api/v1/{path}", headers=_HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def _post(path: str, payload: dict | None = None) -> dict | list:
    r = httpx.post(f"{N8N_URL}/api/v1/{path}", headers=_HEADERS, json=payload or {}, timeout=60)
    r.raise_for_status()
    return r.json()


def _put(path: str, payload: dict | None = None) -> dict | list:
    r = httpx.put(f"{N8N_URL}/api/v1/{path}", headers=_HEADERS, json=payload or {}, timeout=30)
    r.raise_for_status()
    return r.json()


def _delete(path: str) -> str:
    r = httpx.delete(f"{N8N_URL}/api/v1/{path}", headers=_HEADERS, timeout=30)
    r.raise_for_status()
    return "Deleted."


def list_workflows(active: str = "", tags: str = "") -> str:
    """List n8n workflows. Optionally filter by active status ('true'/'false') or comma-separated tag names."""
    params = {}
    if active:
        params["active"] = active
    if tags:
        params["tags"] = tags
    data = _get("workflows", **params)
    workflows = data.get("data", data) if isinstance(data, dict) else data
    if not workflows:
        return "No workflows found."
    lines = []
    for w in workflows[:30]:
        status = "active" if w.get("active") else "inactive"
        tag_list = ", ".join(t.get("name", "") for t in w.get("tags", []))
        tag_str = f" [{tag_list}]" if tag_list else ""
        lines.append(f"  {w['id']}: {w.get('name', '?')} ({status}){tag_str}")
    total = len(workflows)
    suffix = f"\n  ... and {total - 30} more" if total > 30 else ""
    return "\n".join(lines) + suffix


def get_workflow(workflow_id: str) -> str:
    """Get details of a specific n8n workflow by ID, including its nodes and connections."""
    w = _get(f"workflows/{workflow_id}")
    nodes = w.get("nodes", [])
    node_summary = ", ".join(n.get("type", "?").split(".")[-1] for n in nodes[:15])
    if len(nodes) > 15:
        node_summary += f", ... +{len(nodes) - 15} more"
    status = "active" if w.get("active") else "inactive"
    return (f"Workflow '{w.get('name')}' (id={w['id']}, {status})\n"
            f"Nodes ({len(nodes)}): {node_summary}\n"
            f"Created: {w.get('createdAt', '?')}, Updated: {w.get('updatedAt', '?')}")


def activate_workflow(workflow_id: str) -> str:
    """Activate an n8n workflow so its triggers start firing."""
    _post(f"workflows/{workflow_id}/activate")
    return f"Workflow {workflow_id} activated."


def deactivate_workflow(workflow_id: str) -> str:
    """Deactivate an n8n workflow so its triggers stop firing."""
    _post(f"workflows/{workflow_id}/deactivate")
    return f"Workflow {workflow_id} deactivated."


def execute_workflow(workflow_id: str, data: dict = None) -> str:
    """Execute an n8n workflow immediately with optional input data."""
    payload = {}
    if data:
        payload["data"] = data
    result = _post(f"workflows/{workflow_id}/run", payload)
    exec_data = result.get("data", result)
    status = exec_data.get("status", result.get("status", "unknown"))
    exec_id = exec_data.get("id", result.get("id", "?"))
    return f"Execution {exec_id} started (status: {status})."


def list_executions(workflow_id: str = "", status: str = "", limit: int = 10) -> str:
    """List recent n8n workflow executions. Optionally filter by workflow_id or status (success, error, waiting)."""
    params = {"limit": min(limit, 30)}
    if workflow_id:
        params["workflowId"] = workflow_id
    if status:
        params["status"] = status
    data = _get("executions", **params)
    execs = data.get("data", data) if isinstance(data, dict) else data
    if not execs:
        return "No executions found."
    lines = []
    for e in execs:
        wf_name = e.get("workflowData", {}).get("name", e.get("workflowId", "?"))
        lines.append(f"  {e['id']}: workflow={wf_name} status={e.get('status', '?')} "
                     f"started={e.get('startedAt', '?')}")
    return "\n".join(lines)


def get_execution(execution_id: str) -> str:
    """Get details of a specific execution including its output data."""
    e = _get(f"executions/{execution_id}")
    wf_name = e.get("workflowData", {}).get("name", e.get("workflowId", "?"))
    status = e.get("status", "?")
    started = e.get("startedAt", "?")
    finished = e.get("stoppedAt", "?")
    result_data = e.get("data", {})
    result_json = result_data.get("resultData", {})
    last_node = result_json.get("lastNodeExecuted", "?")
    error_msg = result_json.get("error", {}).get("message", "") if isinstance(result_json.get("error"), dict) else ""
    summary = (f"Execution {e['id']}: workflow='{wf_name}' status={status}\n"
               f"Started: {started}, Finished: {finished}\n"
               f"Last node: {last_node}")
    if error_msg:
        summary += f"\nError: {error_msg}"
    return summary


def delete_workflow(workflow_id: str) -> str:
    """Delete an n8n workflow permanently."""
    return _delete(f"workflows/{workflow_id}") + f" Workflow {workflow_id} removed."


def create_workflow(name: str, nodes: list = None, connections: dict = None,
                    active: bool = False) -> str:
    """Create a new n8n workflow. Provide a name and optionally nodes/connections structure."""
    payload = {
        "name": name,
        "nodes": nodes or [],
        "connections": connections or {},
        "active": active,
        "settings": {},
    }
    w = _post("workflows", payload)
    return f"Created workflow '{w.get('name')}' (id={w.get('id')})."


def trigger_webhook(webhook_path: str, method: str = "GET", data: dict = None) -> str:
    """Trigger an n8n webhook by its path. The path is the part after /webhook/ in the webhook URL."""
    url = f"{N8N_URL}/webhook/{webhook_path.lstrip('/')}"
    if method.upper() == "POST":
        r = httpx.post(url, json=data or {}, timeout=60)
    else:
        r = httpx.get(url, params=data or {}, timeout=60)
    return f"{r.status_code}\n{r.text[:3000]}"


TOOLS = [
    Tool(list_workflows, {
        "name": "list_workflows",
        "description": list_workflows.__doc__,
        "input_schema": {
            "type": "object",
            "properties": {
                "active": {"type": "string", "description": "'true' or 'false' to filter by status"},
                "tags": {"type": "string", "description": "Comma-separated tag names to filter by"},
            },
        },
    }),
    Tool(get_workflow, {
        "name": "get_workflow",
        "description": get_workflow.__doc__,
        "input_schema": {
            "type": "object",
            "properties": {"workflow_id": {"type": "string"}},
            "required": ["workflow_id"],
        },
    }),
    Tool(activate_workflow, {
        "name": "activate_workflow",
        "description": activate_workflow.__doc__,
        "input_schema": {
            "type": "object",
            "properties": {"workflow_id": {"type": "string"}},
            "required": ["workflow_id"],
        },
    }),
    Tool(deactivate_workflow, {
        "name": "deactivate_workflow",
        "description": deactivate_workflow.__doc__,
        "input_schema": {
            "type": "object",
            "properties": {"workflow_id": {"type": "string"}},
            "required": ["workflow_id"],
        },
    }),
    Tool(execute_workflow, {
        "name": "execute_workflow",
        "description": execute_workflow.__doc__,
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string"},
                "data": {"type": "object", "description": "Optional input data to pass to the workflow"},
            },
            "required": ["workflow_id"],
        },
    }),
    Tool(list_executions, {
        "name": "list_executions",
        "description": list_executions.__doc__,
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string"},
                "status": {"type": "string", "enum": ["success", "error", "waiting"]},
                "limit": {"type": "integer"},
            },
        },
    }),
    Tool(get_execution, {
        "name": "get_execution",
        "description": get_execution.__doc__,
        "input_schema": {
            "type": "object",
            "properties": {"execution_id": {"type": "string"}},
            "required": ["execution_id"],
        },
    }),
    Tool(create_workflow, {
        "name": "create_workflow",
        "description": create_workflow.__doc__,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "nodes": {"type": "array", "description": "n8n node definitions"},
                "connections": {"type": "object", "description": "n8n node connections"},
                "active": {"type": "boolean"},
            },
            "required": ["name"],
        },
    }),
    Tool(delete_workflow, {
        "name": "delete_workflow",
        "description": delete_workflow.__doc__,
        "input_schema": {
            "type": "object",
            "properties": {"workflow_id": {"type": "string"}},
            "required": ["workflow_id"],
        },
    }),
    Tool(trigger_webhook, {
        "name": "trigger_webhook",
        "description": trigger_webhook.__doc__,
        "input_schema": {
            "type": "object",
            "properties": {
                "webhook_path": {"type": "string", "description": "The path portion after /webhook/ in the URL"},
                "method": {"type": "string", "enum": ["GET", "POST"]},
                "data": {"type": "object"},
            },
            "required": ["webhook_path"],
        },
    }),
]

ROLE = """You are Grik's workflow automation specialist. You manage an n8n
instance — listing, creating, executing, activating, and deactivating workflows,
checking execution history, and triggering webhooks.

Interpret the user's instruction and use your tools to carry it out. When they
say "run my backup workflow" or "show me failed executions", find the right
workflow and act. For ambiguous requests, list workflows first to identify the
right one.

Report what you did in a short, plain summary. Report errors plainly."""

app = make_agent_app("n8n", ROLE, TOOLS)
