# Architecture

## Overview

GMS-MCP is built around one inescapable physical constraint:
`import DigitalMicrograph as DM` succeeds **only inside the GMS host process**.
Everything else flows from this fact.

```
┌─────────────────────────────────────────────────────────────────┐
│  Your workstation (or any networked PC)                         │
│                                                                  │
│  ┌────────────────────┐      ┌──────────────────────────────┐   │
│  │  Ollama LLM        │      │  Claude.ai (remote)          │   │
│  │  (local, port 11434│      │  (HTTPS connector)           │   │
│  └────────┬───────────┘      └──────────────┬───────────────┘   │
│           │ LangChain ReAct agent            │                   │
│           ▼                                 ▼                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │           FastMCP Server  (gms_mcp/server.py)           │    │
│  │   transport: stdio  ──OR──  Streamable HTTP :8000/mcp   │    │
│  │                                                         │    │
│  │   21 tools with Pydantic v2 validation                  │    │
│  │   ┌──────────┐  ┌──────────┐  ┌──────────┐             │    │
│  │   │Acquisition│  │  Stage   │  │ Analysis │  ...        │    │
│  │   └──────────┘  └──────────┘  └──────────┘             │    │
│  └────────────────────────┬────────────────────────────────┘    │
└───────────────────────────│─────────────────────────────────────┘
                            │ ZeroMQ TCP (port 5555)
┌───────────────────────────│─────────────────────────────────────┐
│  Microscope PC (GMS host) │                                      │
│                           ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  DM Bridge Plugin  (gms_mcp/dm_plugin.py)               │    │
│  │  Runs as a daemon thread inside the GMS Python process  │    │
│  │  REP socket: polls for commands, executes DM.* calls    │    │
│  └────────────────────────┬────────────────────────────────┘    │
│                           │  DigitalMicrograph Python API        │
│  ┌────────────────────────▼────────────────────────────────┐    │
│  │  GMS 3.60 process (DigitalMicrograph.exe)               │    │
│  │  Camera, DigiScan, EELS, Stage, Optics, Aberration Corr │    │
│  └────────────────────────┬────────────────────────────────┘    │
└───────────────────────────│─────────────────────────────────────┘
                            │ Hardware interfaces
                   ┌────────▼────────┐
                   │  TEM / STEM     │
                   │  column + detectors │
                   └─────────────────┘
```

---

## Component Responsibilities

### FastMCP Server (`server.py`)

- Runs as a **standalone Python process** (Python 3.10–3.12)
- Registers 21 tools via `@mcp.tool` decorator
- Validates every tool input with a Pydantic v2 model **before** issuing
  any hardware command
- Uses direct `DigitalMicrograph` calls inside GMS, `DMSimulator` in simulation mode,
  and an optional ZeroMQ bridge path for persistent live-processing jobs when `GMS_MCP_ZMQ` is set
- Supports two transports:
  - **stdio** — launched as a subprocess by `MultiServerMCPClient`
    (Ollama/LangChain use case)
  - **Streamable HTTP** — listens on `0.0.0.0:8000/mcp`
    (Claude.ai remote connector use case)
- In simulation mode (`GMS_SIMULATE=1` or `DigitalMicrograph` unavailable), calls
  `DMSimulator` directly
- When `GMS_MCP_ZMQ=tcp://host:5555` is configured, delegates live-job lifecycle requests
  (`start/status/result/stop`) to the DM bridge so persistent processing remains inside the GMS host process

### DM Bridge Plugin (`dm_plugin.py`)

- Runs as a **daemon thread inside the GMS Python process**
- Binds a ZeroMQ `REP` socket on `tcp://0.0.0.0:5555`
- Polls with 500 ms timeout, calling `DM.DoEvents()` each cycle
  to keep the GMS UI responsive
- Dispatches JSON commands to the corresponding `DM.*` API calls
- Maintains its own persistent live-job registry for bridge-backed live analysis
- Serialises results (including NumPy arrays as base64) back to JSON

### DMSimulator (`simulator.py`)

Drop-in replacement for `DigitalMicrograph` activated when:
- `GMS_SIMULATE=1` environment variable is set, **or**
- `import DigitalMicrograph` raises `ImportError`

Implements the full `CM_*`, `DS_*`, `EM_*`, `IF_*`, `IFC_*` API surfaces
with a stateful `MicroscopeState` dataclass. Physical clamping (e.g.
`alpha_max = ±80°`) is enforced identically to real hardware.

**Synthetic data generators:**

| Modality | Generator |
|---|---|
| TEM/HRTEM | Sum of 2D sinusoids + Gaussian noise |
| HAADF-STEM | Poisson background + randomised nanoparticle discs |
| Diffraction | Polycrystalline rings from 5 d-spacings + Poisson noise |
| EELS | ZLP + plasmon peaks + Ti L-edge + Poisson noise |
| 4D-STEM | Convergent-beam disc shifted by probe position |

### Ollama Client (`client.py`)

- Creates a `MultiServerMCPClient` configured for stdio transport
- Instantiates a `LangGraph` ReAct agent with `ChatOllama`
- Maintains full conversation history for multi-turn sessions
- The system prompt encodes the operating protocol:
  always call `gms_get_microscope_state` first, report physical units,
  flag out-of-range requests

---

## Data Flow: Single Tool Call

```
1. User types: "Acquire a HAADF STEM image at 512×512, 10 µs dwell"

2. ChatOllama generates a tool call:
   {
     "name": "gms_acquire_stem",
     "args": {"width": 512, "height": 512, "dwell_us": 10.0, "signals": [0]}
   }

3. LangChain dispatches to MultiServerMCPClient
   → sends MCP tool-call request over stdio/HTTP

4. FastMCP server receives the request
   → constructs AcquireSTEMInput(**args)
   → Pydantic validates bounds (width ∈ [64,4096], dwell_us ∈ [0.5,10000])
   → sends JSON to ZeroMQ bridge: {"function": "DS_Acquire", "params": {...}}

5. DM bridge receives the command
   → calls DM.DSSetFrameSize(512, 512)
   → calls DM.DSSetPixelTime(10.0)
   → calls DM.DSSetSignalEnabled(0, 1)
   → calls DM.DSStartAcquisition()
   → calls DM.DSWaitUntilFinished()
   → reads the front image, computes statistics
   → returns {"success": true, "shape": [512, 512], "mean": 487.3, ...}

6. FastMCP server serialises the response as JSON
   → sends MCP tool result back to the agent

7. ChatOllama receives the tool result
   → synthesises: "Acquired 512×512 HAADF image. Mean intensity: 487
     counts. Total frame time: 2.62 s. Pixel calibration: 0.0196 nm/px."
```

---

## Transport Selection

| Scenario | Transport | Configuration |
|---|---|---|
| Local Ollama development | stdio | default |
| Local Ollama + live GMS | stdio + ZeroMQ | `GMS_MCP_ZMQ=tcp://...` |
| Claude.ai remote connector | Streamable HTTP | `--transport http --port 8000` |
| Air-gapped facility | stdio only | no internet required |

---

## Security Model

The current implementation assumes a **trusted LAN**. The ZeroMQ socket
is unauthenticated. For production deployment in a shared-user facility:

1. Bind the ZeroMQ socket to `127.0.0.1` (localhost only) if the MCP
   server runs on the same machine as GMS.
2. Use a firewall to restrict port 5555 to specific source IPs.
3. For the HTTP transport, place GMS-MCP behind an nginx/Caddy reverse
   proxy with TLS termination and HTTP Basic Auth or OAuth2.

Authentication support (OAuth 2.1 via `fastmcp.server.auth.OAuthProxy`)
is planned for v0.2.0.
