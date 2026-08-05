"""
n8n agent — Wullie's workflow automation specialist.

Talks to an n8n instance via its REST API (v1).
Set N8N_URL and N8N_API_KEY.

Supports auto-provisioning: when Wullie receives a task that should be an
automated workflow, this agent can find similar existing workflows and
extend them, or build a new one from node templates.
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

# ── n8n node templates ───────────────────────────────────────────────
# Pre-built node definitions for common n8n patterns. The LLM picks the
# right ones, fills in parameters, wires them together, and calls
# create_workflow or update_workflow.

NODE_TEMPLATES = {
    "schedule_trigger": {
        "type": "n8n-nodes-base.scheduleTrigger",
        "parameters": {"rule": {"interval": [{"field": "hours", "hoursInterval": 1}]}},
    },
    "cron_trigger": {
        "type": "n8n-nodes-base.scheduleTrigger",
        "parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": "0 9 * * *"}]}},
    },
    "webhook_trigger": {
        "type": "n8n-nodes-base.webhook",
        "parameters": {"path": "my-hook", "httpMethod": "POST"},
    },
    "http_request": {
        "type": "n8n-nodes-base.httpRequest",
        "parameters": {"method": "GET", "url": "https://example.com", "options": {}},
    },
    "if_condition": {
        "type": "n8n-nodes-base.if",
        "parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                                       "conditions": [{"leftValue": "={{ $json.value }}", "rightValue": "", "operator": {"type": "string", "operation": "equals"}}],
                                       "combinator": "and"}},
    },
    "switch": {
        "type": "n8n-nodes-base.switch",
        "parameters": {"rules": {"values": []}},
    },
    "set_data": {
        "type": "n8n-nodes-base.set",
        "parameters": {"mode": "manual", "duplicateItem": False,
                        "assignments": {"assignments": [{"name": "key", "value": "value", "type": "string"}]}},
    },
    "code": {
        "type": "n8n-nodes-base.code",
        "parameters": {"jsCode": "// Process items\nreturn items;", "mode": "runOnceForAllItems"},
    },
    "send_email": {
        "type": "n8n-nodes-base.emailSend",
        "parameters": {"fromEmail": "", "toEmail": "", "subject": "", "text": ""},
    },
    "slack_message": {
        "type": "n8n-nodes-base.slack",
        "parameters": {"resource": "message", "operation": "post", "channel": "", "text": ""},
    },
    "wait": {
        "type": "n8n-nodes-base.wait",
        "parameters": {"amount": 1, "unit": "minutes"},
    },
    "merge": {
        "type": "n8n-nodes-base.merge",
        "parameters": {"mode": "append"},
    },
    "split_in_batches": {
        "type": "n8n-nodes-base.splitInBatches",
        "parameters": {"batchSize": 10},
    },
    "no_op": {
        "type": "n8n-nodes-base.noOp",
        "parameters": {},
    },
    "respond_to_webhook": {
        "type": "n8n-nodes-base.respondToWebhook",
        "parameters": {"respondWith": "json", "responseBody": "={{ $json }}"},
    },
    "home_assistant": {
        "type": "n8n-nodes-base.httpRequest",
        "parameters": {"method": "POST", "url": "http://homeassistant:8123/api/services/light/turn_on",
                        "headerParameters": {"parameters": [{"name": "Authorization", "value": "Bearer YOUR_TOKEN"},
                                                             {"name": "Content-Type", "value": "application/json"}]},
                        "options": {}},
    },
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


def _fetch_all_workflows() -> list[dict]:
    data = _get("workflows")
    return data.get("data", data) if isinstance(data, dict) else data


# ── existing management tools ────────────────────────────────────────

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


# ── auto-provisioning tools ──────────────────────────────────────────

def find_similar_workflows(description: str) -> str:
    """Search existing workflows for ones similar to the described task.
    Compares against workflow names, node types, and tag names.
    Returns matching workflows with their structure so you can decide
    whether to duplicate and extend one rather than building from scratch."""
    keywords = set(description.lower().split())
    workflows = _fetch_all_workflows()
    if not workflows:
        return "No existing workflows to compare against."

    scored = []
    for w in workflows:
        score = 0
        name_lower = w.get("name", "").lower()
        for kw in keywords:
            if kw in name_lower:
                score += 3
        tags = [t.get("name", "").lower() for t in w.get("tags", [])]
        for kw in keywords:
            if any(kw in tag for tag in tags):
                score += 2
        nodes = w.get("nodes", [])
        node_types = " ".join(n.get("type", "").lower() for n in nodes)
        node_names = " ".join(n.get("name", "").lower() for n in nodes)
        for kw in keywords:
            if kw in node_types or kw in node_names:
                score += 1
        if score > 0:
            scored.append((score, w))

    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored:
        return "No similar workflows found. Build a new one."

    lines = []
    for score, w in scored[:5]:
        nodes = w.get("nodes", [])
        node_types = [n.get("type", "?").split(".")[-1] for n in nodes]
        tag_list = ", ".join(t.get("name", "") for t in w.get("tags", []))
        status = "active" if w.get("active") else "inactive"
        lines.append(
            f"  id={w['id']} score={score} \"{w.get('name')}\" ({status})"
            f"\n    nodes: {', '.join(node_types[:10])}"
            + (f"\n    tags: {tag_list}" if tag_list else "")
        )
    return "Similar workflows found:\n" + "\n".join(lines)


def duplicate_workflow(workflow_id: str, new_name: str) -> str:
    """Duplicate an existing workflow under a new name. Returns the new workflow's
    ID so you can then modify it with update_workflow. Use this to build off an
    existing workflow rather than starting from scratch."""
    source = _get(f"workflows/{workflow_id}")
    payload = {
        "name": new_name,
        "nodes": source.get("nodes", []),
        "connections": source.get("connections", {}),
        "settings": source.get("settings", {}),
        "active": False,
    }
    w = _post("workflows", payload)
    node_count = len(payload["nodes"])
    return (f"Duplicated workflow '{source.get('name')}' -> '{w.get('name')}' "
            f"(new id={w.get('id')}, {node_count} nodes). Modify it with update_workflow.")


def update_workflow(workflow_id: str, name: str = "", nodes: list = None,
                    connections: dict = None) -> str:
    """Update an existing workflow's name, nodes, and/or connections. Use this
    to modify a duplicated workflow or add nodes to an existing one. Only
    provided fields are changed."""
    current = _get(f"workflows/{workflow_id}")
    payload = {
        "name": name or current.get("name"),
        "nodes": nodes if nodes is not None else current.get("nodes", []),
        "connections": connections if connections is not None else current.get("connections", {}),
        "settings": current.get("settings", {}),
    }
    w = _put(f"workflows/{workflow_id}", payload)
    node_count = len(payload["nodes"])
    return f"Updated workflow '{w.get('name')}' (id={workflow_id}, {node_count} nodes)."


def get_workflow_full(workflow_id: str) -> str:
    """Get the complete JSON structure of a workflow including all node parameters
    and connections. Use this to understand an existing workflow's structure before
    duplicating or modifying it."""
    w = _get(f"workflows/{workflow_id}")
    nodes = w.get("nodes", [])
    connections = w.get("connections", {})
    node_details = []
    for n in nodes:
        node_details.append({
            "name": n.get("name"),
            "type": n.get("type"),
            "position": n.get("position"),
            "parameters": n.get("parameters", {}),
        })
    return json.dumps({"id": w["id"], "name": w.get("name"),
                        "nodes": node_details, "connections": connections}, indent=2)[:6000]


def list_node_templates() -> str:
    """List available node templates that can be used to build workflows.
    Each template is a pre-configured n8n node type. Use get_node_template
    to get the full JSON for a template, then customize its parameters."""
    lines = []
    descriptions = {
        "schedule_trigger": "Run on an interval (hours, minutes, etc.)",
        "cron_trigger": "Run on a cron schedule (e.g. daily at 9am)",
        "webhook_trigger": "Triggered by an incoming HTTP request",
        "http_request": "Make an HTTP request to any API",
        "if_condition": "Branch based on a condition (if/else)",
        "switch": "Route to different branches based on value matching",
        "set_data": "Set or transform data fields",
        "code": "Run custom JavaScript code",
        "send_email": "Send an email (requires SMTP credentials)",
        "slack_message": "Post a message to Slack",
        "wait": "Pause execution for a duration",
        "merge": "Merge data from multiple branches",
        "split_in_batches": "Process items in batches",
        "no_op": "No operation (useful as a junction node)",
        "respond_to_webhook": "Send a response back to a webhook caller",
        "home_assistant": "Call a Home Assistant service via HTTP",
    }
    for key in NODE_TEMPLATES:
        desc = descriptions.get(key, "")
        lines.append(f"  {key}: {desc}")
    return "Available node templates:\n" + "\n".join(lines)


def get_node_template(template_name: str, node_name: str = "",
                      parameter_overrides: dict = None) -> str:
    """Get a node template's JSON definition, optionally customizing its name and
    parameters. Returns the full node object ready to be included in a workflow's
    nodes array. Use parameter_overrides to set specific values (e.g.
    {'url': 'https://api.example.com', 'method': 'POST'})."""
    template = NODE_TEMPLATES.get(template_name)
    if not template:
        return f"Unknown template '{template_name}'. Use list_node_templates to see available ones."
    node = {
        "name": node_name or template_name.replace("_", " ").title(),
        "type": template["type"],
        "typeVersion": 1,
        "position": [0, 0],
        "parameters": {**template["parameters"]},
    }
    if parameter_overrides:
        _deep_merge(node["parameters"], parameter_overrides)
    return json.dumps(node, indent=2)


def _deep_merge(base: dict, overrides: dict):
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def add_nodes_to_workflow(workflow_id: str, new_nodes: list,
                          append_after_node: str = "") -> str:
    """Add new nodes to an existing workflow and auto-wire them. Nodes are
    appended to the workflow. If append_after_node is given (a node name),
    the first new node is connected after it in the flow. New nodes are
    connected sequentially to each other."""
    current = _get(f"workflows/{workflow_id}")
    existing_nodes = current.get("nodes", [])
    connections = current.get("connections", {})

    max_x = max((n.get("position", [0, 0])[0] for n in existing_nodes), default=0)
    base_x = max_x + 250
    for i, node in enumerate(new_nodes):
        if node.get("position", [0, 0]) == [0, 0]:
            node["position"] = [base_x + i * 250, 300]
        if "typeVersion" not in node:
            node["typeVersion"] = 1

    if append_after_node and new_nodes:
        connections.setdefault(append_after_node, {})
        connections[append_after_node].setdefault("main", [[]])
        connections[append_after_node]["main"][0].append({
            "node": new_nodes[0]["name"],
            "type": "main",
            "index": 0,
        })

    for i in range(len(new_nodes) - 1):
        src_name = new_nodes[i]["name"]
        dst_name = new_nodes[i + 1]["name"]
        connections.setdefault(src_name, {})
        connections[src_name].setdefault("main", [[]])
        connections[src_name]["main"][0].append({
            "node": dst_name,
            "type": "main",
            "index": 0,
        })

    all_nodes = existing_nodes + new_nodes
    payload = {
        "name": current.get("name"),
        "nodes": all_nodes,
        "connections": connections,
        "settings": current.get("settings", {}),
    }
    w = _put(f"workflows/{workflow_id}", payload)
    return (f"Added {len(new_nodes)} node(s) to workflow '{w.get('name')}' "
            f"(id={workflow_id}, now {len(all_nodes)} nodes total).")


# ── tool registration ────────────────────────────────────────────────

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
    Tool(get_workflow_full, {
        "name": "get_workflow_full",
        "description": get_workflow_full.__doc__,
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
    Tool(find_similar_workflows, {
        "name": "find_similar_workflows",
        "description": find_similar_workflows.__doc__,
        "input_schema": {
            "type": "object",
            "properties": {"description": {"type": "string", "description": "Plain-language description of the task to search for"}},
            "required": ["description"],
        },
    }),
    Tool(duplicate_workflow, {
        "name": "duplicate_workflow",
        "description": duplicate_workflow.__doc__,
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string"},
                "new_name": {"type": "string"},
            },
            "required": ["workflow_id", "new_name"],
        },
    }),
    Tool(update_workflow, {
        "name": "update_workflow",
        "description": update_workflow.__doc__,
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string"},
                "name": {"type": "string"},
                "nodes": {"type": "array", "description": "Complete list of node definitions (replaces existing)"},
                "connections": {"type": "object", "description": "Complete connections object (replaces existing)"},
            },
            "required": ["workflow_id"],
        },
    }),
    Tool(add_nodes_to_workflow, {
        "name": "add_nodes_to_workflow",
        "description": add_nodes_to_workflow.__doc__,
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string"},
                "new_nodes": {"type": "array", "description": "List of node objects to add"},
                "append_after_node": {"type": "string", "description": "Name of existing node to wire the first new node after"},
            },
            "required": ["workflow_id", "new_nodes"],
        },
    }),
    Tool(list_node_templates, {
        "name": "list_node_templates",
        "description": list_node_templates.__doc__,
        "input_schema": {"type": "object", "properties": {}},
    }),
    Tool(get_node_template, {
        "name": "get_node_template",
        "description": get_node_template.__doc__,
        "input_schema": {
            "type": "object",
            "properties": {
                "template_name": {"type": "string"},
                "node_name": {"type": "string", "description": "Display name for the node in n8n"},
                "parameter_overrides": {"type": "object", "description": "Values to override in the template parameters"},
            },
            "required": ["template_name"],
        },
    }),
]

ROLE = """You are Wullie's workflow automation specialist. You manage an n8n
instance — listing, creating, executing, activating, and deactivating workflows,
checking execution history, and triggering webhooks.

AUTO-PROVISIONING WORKFLOWS
When asked to automate a task as a workflow, follow this process:

1. SEARCH FIRST: Use find_similar_workflows to check for existing workflows
   that already do something similar. Prefer extending what exists over
   building from scratch.

2. IF SIMILAR EXISTS: Use duplicate_workflow to clone it, then update_workflow
   or add_nodes_to_workflow to adapt it to the new task. This preserves
   tested logic and credentials.

3. IF NOTHING SIMILAR: Build a new workflow:
   a. Use list_node_templates to see available building blocks.
   b. Use get_node_template to get node JSON for each step, customising
      parameters with parameter_overrides.
   c. Assemble the nodes and connections, then call create_workflow.

4. After creating/modifying, always report what the workflow does and
   whether it's active or still needs manual activation.

When the user says "automate X", "set up a workflow for X", or "make it run
every day", that's a workflow provisioning request. When they say "run my
backup workflow" or "show me failed executions", that's a management request.

Report what you did in a short, plain summary. Report errors plainly."""

app = make_agent_app("n8n", ROLE, TOOLS)
