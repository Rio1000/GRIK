"""
AgentManager — Wullie's hands.

Responsibilities:
  * Keep a registry of capabilities -> agent containers.
  * Dispatch a task to the right agent over HTTP.
  * If an agent isn't running yet, start it.
  * If a capability doesn't exist at all, PROVISION a new agent container
    from the generic base-agent image, configured with a role prompt.

Each agent is a small FastAPI service exposing POST /execute
    {"instruction": "...", "context": {...}}  ->  {"result": "..."}
All agents share a Docker network so Wullie can reach them by container name.
"""
from __future__ import annotations

import re
import time
import logging
from dataclasses import dataclass, asdict

import httpx

try:
    import docker
    from docker.errors import NotFound
except ImportError:  # docker SDK optional in text/dev mode
    docker = None
    NotFound = Exception

from .config import config

log = logging.getLogger("wullie.manager")


@dataclass
class AgentSpec:
    capability: str          # short slug, e.g. "media", "web", "home"
    container: str           # docker container name, e.g. "wullie-agent-media"
    image: str               # docker image to run
    port: int = 8000         # port the agent listens on inside the network
    role_prompt: str = ""    # for provisioned generic agents
    env: dict = None         # extra env passed to the container

    def url(self) -> str:
        return f"http://{self.container}:{self.port}/execute"


# Capabilities that ship with Wullie. Provisioned ones get added at runtime.
BUILTIN_AGENTS = {
    "media": AgentSpec(
        capability="media",
        container="wullie-agent-media",
        image="wullie-media-agent:latest",
        port=8000,
        env={},  # RADARR_URL / RADARR_API_KEY etc. come from compose
    ),
    "web": AgentSpec(
        capability="web",
        container="wullie-agent-web",
        image="wullie-web-agent:latest",
        port=8000,
        env={},
    ),
    "home": AgentSpec(
        capability="home",
        container="wullie-agent-home",
        image="wullie-home-agent:latest",
        port=8000,
        env={},  # HASS_URL / HASS_TOKEN come from compose
    ),
    "n8n": AgentSpec(
        capability="n8n",
        container="wullie-agent-n8n",
        image="wullie-n8n-agent:latest",
        port=8000,
        env={},  # N8N_URL / N8N_API_KEY come from compose
    ),
}


class AgentManager:
    def __init__(self):
        self.registry: dict[str, AgentSpec] = dict(BUILTIN_AGENTS)
        self._client = None
        if docker is not None:
            try:
                self._client = docker.from_env()
                self._ensure_network()
            except Exception as e:  # daemon not reachable -> degrade gracefully
                log.warning("Docker daemon unavailable (%s). Provisioning disabled.", e)

    # ---- public API used by the brain --------------------------------------

    def capabilities_summary(self) -> str:
        lines = []
        for spec in self.registry.values():
            note = spec.role_prompt.split("\n")[0] if spec.role_prompt else "built-in specialist"
            lines.append(f"  - {spec.capability}: {note}")
        return "\n".join(lines) if lines else "  (none yet)"

    def delegate(self, capability: str, instruction: str, context: dict | None = None) -> str:
        """Route one task to a specialist agent. Starts it if needed."""
        spec = self.registry.get(capability)
        if spec is None:
            return (f"No agent exists for capability '{capability}'. "
                    f"Provision one first with provision_agent.")
        self._ensure_running(spec)
        return self._call(spec, instruction, context or {})

    def provision_agent(self, capability: str, role_prompt: str,
                        env: dict | None = None) -> str:
        """
        Create a brand-new agent for a capability that doesn't exist yet.
        Uses the generic base-agent image, configured by a role prompt.
        """
        if not config.allow_provisioning:
            return "Provisioning is disabled by config (WULLIE_ALLOW_PROVISIONING=false)."
        if self._client is None:
            return "Cannot provision: Docker daemon is not reachable."

        capability = _slug(capability)
        if capability in self.registry:
            return f"Capability '{capability}' already exists — just delegate to it."

        spec = AgentSpec(
            capability=capability,
            container=f"wullie-agent-{capability}",
            image=config.base_agent_image,
            port=8000,
            role_prompt=role_prompt,
            env=env or {},
        )
        self._ensure_running(spec)
        self.registry[capability] = spec
        return f"Provisioned new agent '{spec.container}' for capability '{capability}'."

    # ---- docker plumbing ----------------------------------------------------

    def _ensure_network(self):
        try:
            self._client.networks.get(config.docker_network)
        except NotFound:
            self._client.networks.create(config.docker_network, driver="bridge")
            log.info("Created docker network %s", config.docker_network)

    def _ensure_running(self, spec: AgentSpec):
        """Guarantee a container for this spec is up and on the network."""
        if self._client is None:
            return  # dev mode: assume the agent is reachable (e.g. via compose)
        try:
            c = self._client.containers.get(spec.container)
            if c.status != "running":
                c.start()
                self._wait_healthy(spec)
            return
        except NotFound:
            pass

        env = {
            "ANTHROPIC_API_KEY": config.anthropic_api_key,
            "WULLIE_BRAIN_MODEL": config.brain_model,
            "AGENT_NAME": spec.capability,
            "AGENT_ROLE_PROMPT": spec.role_prompt,
            **(spec.env or {}),
        }
        log.info("Starting agent container %s (%s)", spec.container, spec.image)
        self._client.containers.run(
            spec.image,
            name=spec.container,
            detach=True,
            network=config.docker_network,
            environment=env,
            restart_policy={"Name": "unless-stopped"},
            labels={"wullie.agent": spec.capability},
        )
        self._wait_healthy(spec)

    def _wait_healthy(self, spec: AgentSpec, tries: int = 30):
        health = f"http://{spec.container}:{spec.port}/health"
        for _ in range(tries):
            try:
                if httpx.get(health, timeout=2).status_code == 200:
                    return
            except Exception:
                pass
            time.sleep(1)
        log.warning("Agent %s did not report healthy in time", spec.container)

    def _call(self, spec: AgentSpec, instruction: str, context: dict) -> str:
        try:
            r = httpx.post(
                spec.url(),
                json={"instruction": instruction, "context": context},
                timeout=config.agent_call_timeout,
            )
            r.raise_for_status()
            return r.json().get("result", "")
        except Exception as e:
            return f"Agent '{spec.capability}' failed: {e}"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9-]", "", name.strip().lower().replace(" ", "-")) or "task"
