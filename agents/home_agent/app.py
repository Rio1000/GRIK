"""
Home Assistant agent — Wullie's smart-home specialist.

Talks to a Home Assistant instance via its REST API.
Set HASS_URL and HASS_TOKEN (a long-lived access token).
"""
import os
import json
import httpx

from agentlib import Tool, make_agent_app

HASS_URL = os.getenv("HASS_URL", "http://homeassistant:8123").rstrip("/")
HASS_TOKEN = os.getenv("HASS_TOKEN", "")

_HEADERS = {
    "Authorization": f"Bearer {HASS_TOKEN}",
    "Content-Type": "application/json",
}


def _get(path: str, **params) -> dict | list:
    r = httpx.get(f"{HASS_URL}/api/{path}", headers=_HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def _post(path: str, payload: dict | None = None) -> dict | list:
    r = httpx.post(f"{HASS_URL}/api/{path}", headers=_HEADERS, json=payload or {}, timeout=30)
    r.raise_for_status()
    return r.json() if r.text else {}


def get_state(entity_id: str) -> str:
    """Get the current state and attributes of a Home Assistant entity (e.g. light.living_room)."""
    data = _get(f"states/{entity_id}")
    attrs = data.get("attributes", {})
    friendly = attrs.get("friendly_name", entity_id)
    state = data.get("state", "unknown")
    useful_attrs = {k: v for k, v in attrs.items()
                    if k in ("brightness", "color_temp", "rgb_color", "temperature",
                             "current_temperature", "hvac_action", "hvac_modes",
                             "unit_of_measurement", "device_class", "friendly_name")}
    return f"{friendly}: {state}" + (f" ({json.dumps(useful_attrs)})" if useful_attrs else "")


def list_entities(domain: str = "") -> str:
    """List Home Assistant entities, optionally filtered by domain (light, switch, climate, sensor, etc.)."""
    states = _get("states")
    if domain:
        states = [s for s in states if s["entity_id"].startswith(f"{domain}.")]
    lines = []
    for s in states[:60]:
        name = s.get("attributes", {}).get("friendly_name", s["entity_id"])
        lines.append(f"{s['entity_id']}: {s['state']} ({name})")
    total = len(states)
    suffix = f"\n... and {total - 60} more" if total > 60 else ""
    return "\n".join(lines) + suffix if lines else f"No entities found for domain '{domain}'."


def call_service(domain: str, service: str, entity_id: str = "",
                 data: dict = None) -> str:
    """Call a Home Assistant service (e.g. domain='light', service='turn_on', entity_id='light.living_room').
    Optional data dict for extra parameters like brightness, color_temp, temperature, etc."""
    payload = {}
    if entity_id:
        payload["entity_id"] = entity_id
    if data:
        payload.update(data)
    result = _post(f"services/{domain}/{service}", payload)
    target = entity_id or f"{domain}.{service}"
    return f"Called {domain}.{service} on {target}. " + (
        f"Affected {len(result)} entities." if isinstance(result, list) else "Done.")


def turn_on(entity_id: str, brightness_pct: int = 0, color_temp: int = 0) -> str:
    """Turn on a light or switch. For lights: optionally set brightness_pct (1-100) and/or color_temp (mireds)."""
    domain = entity_id.split(".")[0]
    data = {}
    if domain == "light":
        if brightness_pct:
            data["brightness_pct"] = max(1, min(100, brightness_pct))
        if color_temp:
            data["color_temp"] = color_temp
    payload = {"entity_id": entity_id, **data}
    _post(f"services/{domain}/turn_on", payload)
    extras = []
    if brightness_pct:
        extras.append(f"brightness {brightness_pct}%")
    if color_temp:
        extras.append(f"color temp {color_temp}")
    detail = f" ({', '.join(extras)})" if extras else ""
    return f"Turned on {entity_id}{detail}."


def turn_off(entity_id: str) -> str:
    """Turn off a light, switch, fan, or other toggleable entity."""
    domain = entity_id.split(".")[0]
    _post(f"services/{domain}/turn_off", {"entity_id": entity_id})
    return f"Turned off {entity_id}."


def set_climate(entity_id: str, temperature: float = 0, hvac_mode: str = "") -> str:
    """Set a climate entity's target temperature and/or HVAC mode (heat, cool, auto, off)."""
    if hvac_mode:
        _post("services/climate/set_hvac_mode",
              {"entity_id": entity_id, "hvac_mode": hvac_mode})
    if temperature:
        _post("services/climate/set_temperature",
              {"entity_id": entity_id, "temperature": temperature})
    parts = []
    if hvac_mode:
        parts.append(f"mode={hvac_mode}")
    if temperature:
        parts.append(f"target={temperature}")
    return f"Climate {entity_id} set: {', '.join(parts)}."


def activate_scene(entity_id: str) -> str:
    """Activate a Home Assistant scene (e.g. scene.movie_night)."""
    _post("services/scene/turn_on", {"entity_id": entity_id})
    return f"Activated {entity_id}."


def trigger_automation(entity_id: str) -> str:
    """Trigger a Home Assistant automation manually."""
    _post("services/automation/trigger", {"entity_id": entity_id})
    return f"Triggered {entity_id}."


def fire_event(event_type: str, event_data: dict = None) -> str:
    """Fire a custom Home Assistant event."""
    _post(f"events/{event_type}", event_data or {})
    return f"Fired event '{event_type}'."


TOOLS = [
    Tool(get_state, {
        "name": "get_state",
        "description": get_state.__doc__,
        "input_schema": {
            "type": "object",
            "properties": {"entity_id": {"type": "string"}},
            "required": ["entity_id"],
        },
    }),
    Tool(list_entities, {
        "name": "list_entities",
        "description": list_entities.__doc__,
        "input_schema": {
            "type": "object",
            "properties": {"domain": {"type": "string", "description": "e.g. light, switch, sensor, climate, cover, fan, media_player"}},
        },
    }),
    Tool(call_service, {
        "name": "call_service",
        "description": call_service.__doc__,
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string"},
                "service": {"type": "string"},
                "entity_id": {"type": "string"},
                "data": {"type": "object"},
            },
            "required": ["domain", "service"],
        },
    }),
    Tool(turn_on, {
        "name": "turn_on",
        "description": turn_on.__doc__,
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string"},
                "brightness_pct": {"type": "integer"},
                "color_temp": {"type": "integer"},
            },
            "required": ["entity_id"],
        },
    }),
    Tool(turn_off, {
        "name": "turn_off",
        "description": turn_off.__doc__,
        "input_schema": {
            "type": "object",
            "properties": {"entity_id": {"type": "string"}},
            "required": ["entity_id"],
        },
    }),
    Tool(set_climate, {
        "name": "set_climate",
        "description": set_climate.__doc__,
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string"},
                "temperature": {"type": "number"},
                "hvac_mode": {"type": "string", "enum": ["heat", "cool", "auto", "off", "heat_cool", "fan_only", "dry"]},
            },
            "required": ["entity_id"],
        },
    }),
    Tool(activate_scene, {
        "name": "activate_scene",
        "description": activate_scene.__doc__,
        "input_schema": {
            "type": "object",
            "properties": {"entity_id": {"type": "string"}},
            "required": ["entity_id"],
        },
    }),
    Tool(trigger_automation, {
        "name": "trigger_automation",
        "description": trigger_automation.__doc__,
        "input_schema": {
            "type": "object",
            "properties": {"entity_id": {"type": "string"}},
            "required": ["entity_id"],
        },
    }),
    Tool(fire_event, {
        "name": "fire_event",
        "description": fire_event.__doc__,
        "input_schema": {
            "type": "object",
            "properties": {
                "event_type": {"type": "string"},
                "event_data": {"type": "object"},
            },
            "required": ["event_type"],
        },
    }),
]

ROLE = """You are Wullie's smart-home specialist. You control a Home Assistant
instance — lights, switches, climate, covers, fans, media players, scenes,
automations, and sensors.

Interpret the user's instruction and use your tools to carry it out. When
they say "turn on the lights" or "dim the bedroom", figure out the right
entity_id from the available entities (list them first if unsure) and act.

For ambiguous requests, list matching entities and pick the best fit.
Report what you did in a short, plain summary. Report errors plainly."""

app = make_agent_app("home", ROLE, TOOLS)
