# Grik — General Roaming of Internet Knowledge

A voice-first, Jarvis-style assistant with a warm Celtic lilt. Grik doesn't try
to do everything itself — it's an **orchestrator** that hands real work to
specialist **agents**, each running in its own Docker container. If a task has
no matching agent, Grik can **provision a new one on the spot**.

```
        "Hey Grik..."
             │
        ┌────▼─────┐  wake word (Porcupine, local)
        │  VOICE   │  speech-to-text (faster-whisper, local)
        │  LOOP    │  text-to-speech (ElevenLabs, Celtic voice)
        └────┬─────┘
        ┌────▼─────┐  the brain: understands, splits, delegates
        │   GRIK   │──────────────┐
        │  (brain) │              │ provisions if missing
        └────┬─────┘              ▼
             │ delegate     ┌─────────────┐
   ┌─────────┼─────────┐    │ base-agent  │  ← cloned into a new
   ▼         ▼         ▼    │  (generic)  │    container per new task
┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ └─────────────┘
│media │ │ web  │ │ home │ │ n8n  │  each an isolated Docker
│agent │ │agent │ │agent │ │agent │  container, POST /execute
└──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘
Radarr    search+   Home     workflow
Sonarr    fetch     Asst.    automation
```

## The Celtic bit — how it stays *understandable*

The character comes from two independent layers, so it never turns to mush:

- **Grammar / word choice** lives in `grik/personality.py`. A light Hiberno/Scots
  register ("aye", "wee", "grand", "no bother", "...so") applied only to the
  *connective tissue*. Technical content — filenames, commands, IDs, errors — is
  quoted plainly and never dialect-ified. It also drops the flavour when you're
  stressed or something breaks.
- **Accent** lives in `grik/voice/tts.py`. Pick (or design) an Irish/Scottish
  voice in ElevenLabs and set `GRIK_VOICE_ID`. That's what carries the lilt in
  the ear; the text stays readable on screen.

## What's in the box

| Piece | File | Notes |
|---|---|---|
| Wake word | `grik/voice/wakeword.py` | Porcupine; only wakes on "Grik"/"Hey Grik". Audio is local until then. |
| STT | `grik/voice/stt.py` | Local faster-whisper — your speech isn't shipped off for transcription. |
| TTS | `grik/voice/tts.py` | ElevenLabs streaming, low latency. |
| Brain | `grik/brain.py` | Anthropic tool-use loop: delegate / provision. |
| Agent manager | `grik/manager.py` | Docker SDK: registry, start, and provision containers. |
| Agent runtime | `common/agentlib.py` | Turns (name + prompt + tools) into a FastAPI agent. |
| Media agent | `agents/media_agent/` | Radarr + Sonarr. Copy the pattern for Lidarr, Prowlarr, Overseerr, Bazarr... |
| Web agent | `agents/web_agent/` | Search (SearXNG) + fetch-and-read. |
| Home agent | `agents/home_agent/` | Home Assistant: lights, switches, climate, scenes, automations, sensors. |
| n8n agent | `agents/n8n_agent/` | n8n: list/run/create workflows, check executions, trigger webhooks. |
| Base agent | `agents/base_agent/` | The blank specialist that gets cloned for new capabilities. |

## Setup

1. `cp .env.example .env` and fill in keys: `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`
   + `GRIK_VOICE_ID`, `PICOVOICE_ACCESS_KEY`, `RADARR_API_KEY`, `HASS_TOKEN`,
   `N8N_API_KEY`, etc.
2. Train a wake word: at <https://console.picovoice.ai> make a custom "Grik"
   (and/or "Hey Grik") keyword, download the `.ppn`, and point `GRIK_WAKE_PPN` at it.
3. Build the agent images: `docker compose build`

## Running

**Voice mode (on the host — needs mic, speaker, and Docker socket):**
```bash
pip install -r requirements.txt
python -m grik.main
```
Grik runs on the host so it can reach your audio devices, and talks to the
Docker daemon to manage the agent containers.

**Text mode (great for testing, no audio):**
```bash
GRIK_TEXT_MODE=true python -m grik.main
# or fully in Docker:
docker compose --profile text run --rm grik
```

Try: *"add the film Dune Part Two to the library"*, *"turn on the living room
lights"*, *"set the thermostat to 21 degrees"*, *"run my backup workflow"*,
*"show me failed n8n executions"*, *"what's the weather in Galway"*, or
something with no existing agent — *"track the price of a GPU"* — and watch
Grik provision a new agent for it.

For automation: *"every morning at 8, turn on the kitchen lights and send me
a weather summary on Slack"* — Grik will search for similar existing n8n
workflows, build off one if it finds a match, or assemble a new one from
node templates and activate it.

## Auto-provisioning: agents AND workflows

Grik can self-provision in two ways:

- **New agents** (`provision_agent`): when no existing capability fits a task,
  Grik spins up a new Docker container from the generic base-agent image,
  configured with a role prompt. This gives Grik a new permanent specialist.
- **New workflows** (`automate`): when the user wants something to happen
  *automatically* — on a schedule, via a webhook, or as a reusable automation —
  Grik delegates to the n8n agent, which:
  1. **Searches** existing workflows for a similar one.
  2. **Duplicates and extends** it if one fits, preserving tested logic and
     credentials.
  3. **Builds from scratch** using node templates if nothing similar exists.

  This means saying *"automate a nightly backup"* will reuse your existing
  backup workflow's structure if you have one, rather than creating a
  duplicate from nothing.

## Adding a service (the common case)

Radarr, Sonarr, Lidarr, Prowlarr, Overseerr, Home Assistant — nearly all expose
a REST API with an API key. To add one, copy `agents/media_agent/`, write a few
tool functions hitting that API, register the image in `BUILTIN_AGENTS`
(`grik/manager.py`), and add it to `docker-compose.yml`. That's it.

## Honest caveats (read these)

- **"Full access to everything on the internet"** here means broad, real web
  reach via the web agent (search + fetch). There is no such thing as literally
  unrestricted access — sites gate, auth, and rate-limit — and you wouldn't want
  a voice assistant with unbounded reach anyway. Add credentialed access per
  service, deliberately, via agents.
- **Self-provisioning containers is powerful and a real attack surface.** Grik
  provisioning agents means an LLM decides to start containers and make outbound
  HTTP calls. Mitigations already in place: provisioning is a config flag
  (`GRIK_ALLOW_PROVISIONING`), new agents are the *generic base image* configured
  by a role prompt (not arbitrary generated code), and the base agent's HTTP tool
  restricts methods. Before exposing Grik beyond your LAN you should also: run it
  as a non-root user, drop container capabilities, put agents on an egress-filtered
  network, and consider a rootless Docker socket proxy instead of mounting
  `/var/run/docker.sock` directly. If you later add a code-generation path
  (Grik *writing* new agent code), sandbox the build/run and require a human OK.
- **API drift.** ElevenLabs, Porcupine, faster-whisper and the *arr APIs all move.
  The code targets their current shapes; check their docs if a call 400s.

## Layout
```
grik/
├── grik/            # orchestrator: brain, voice, agent manager
├── common/          # shared agent runtime
├── agents/          # the containerised specialists (media, web, base)
├── docker-compose.yml
├── requirements.txt
└── .env.example
```
