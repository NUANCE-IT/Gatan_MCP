# Live GMS Setup Guide

This guide walks through connecting GMS-MCP to a real Gatan Microscopy Suite
instance and microscope column.

---

## Prerequisites

- GMS 3.60 or later installed on the microscope PC
- Network access between the microscope PC and your workstation
  (same LAN, or VPN)
- Firewall rule allowing TCP port 5555 between the two machines
- Python 3.7+ available in the GMS virtual environment
  (`C:\ProgramData\Miniconda3\envs\GMS_VENV_PYTHON`)

---

## Step 1: Install pyzmq in the GMS environment

Open a Command Prompt **as Administrator** on the microscope PC:

```bat
cd C:\ProgramData\Miniconda3\envs\GMS_VENV_PYTHON
activate GMS_VENV_PYTHON
pip install pyzmq --break-system-packages
```

Verify:

```bat
python -c "import zmq; print(zmq.__version__)"
```

---

## Step 2: Copy the DM bridge plugin

Copy `src/gms_mcp/dm_plugin.py` to a location accessible within GMS,
for example `C:\GMS_Scripts\dm_plugin.py`.

---

## Step 3: Start the ZeroMQ bridge inside GMS

In the GMS Python console (Script → Open Python Console):

```python
# Start the bridge on default port 5555
exec(open("C:/GMS_Scripts/dm_plugin.py").read())
```

Or, if `nuance-gms-mcp` is installed directly inside `GMS_VENV_PYTHON`:

```python
from gms_mcp.dm_plugin import start_bridge
start_bridge()
```

You should see:

```
[GMS-MCP] DM bridge ready on tcp://0.0.0.0:5555
[GMS-MCP] Bridge thread started → tcp://0.0.0.0:5555
```

The bridge runs as a background daemon thread — GMS remains fully
interactive.

To stop the bridge when finished:

```python
stop_bridge()
```

---

## Step 4: Configure the GMS-MCP server

On your workstation, set the ZeroMQ endpoint:

```bash
export GMS_MCP_ZMQ=tcp://192.168.1.100:5555   # replace with microscope PC IP
```

Or in `~/.bashrc` / `~/.zshrc` for persistence.

---

## Step 5: Start the MCP server

Ensure simulation is not forced in your shell:

```bash
unset GMS_SIMULATE
```

**For local Ollama use (stdio):**

```bash
python -m gms_mcp.client
```

**For Claude.ai remote access (HTTP):**

```bash
python -m gms_mcp.server --transport http --host 0.0.0.0 --port 8000
```

---

## Step 6: Verify the connection

In the interactive agent session:

```
You: What is the current microscope state?

Agent: [calls gms_get_microscope_state]
       Connected to live GMS. Microscope at 200 kV, TEM mode,
       spot size 3, stage at X=0 Y=0 Z=0.
```

---

## Network Security Considerations

- The ZeroMQ socket is **unauthenticated** — anyone who can reach port 5555
  can issue microscope commands.
- Restrict the firewall to allow only the IP of the workstation running
  the MCP server.
- For facilities with strict network policies, run both the GMS bridge and
  the MCP server on the same microscope PC (localhost binding):

```python
# In GMS console — bind to localhost only
start_bridge("tcp://127.0.0.1:5555")
```

```bash
# On the same machine
GMS_MCP_ZMQ=tcp://127.0.0.1:5555 python -m gms_mcp.client
```

---

## GMS Version Compatibility

| GMS Version | Status | Notes |
|---|---|---|
| 3.60 | ✅ Tested | Reference version |
| 3.62 | ✅ Expected | No API changes affecting bridge |
| 3.5x | ⚠️ Partial | UnregisterAllListeners missing; avoid live event listeners |
| 3.4x | ⚠️ Partial | execdmscript bridge required for some functions |
| < 3.4 | ❌ | Python integration unavailable |

---

## Common Issues

**GMS freezes when running the bridge**

Use the current bridge implementation and start it with either:

```python
exec(open("C:/GMS_Scripts/dm_plugin.py").read())
```

or:

```python
from gms_mcp.dm_plugin import start_bridge
start_bridge()
```

Do not rely on module import side effects to start the bridge.
If GMS still freezes on startup, verify that you are using the latest
published package or current `dm_plugin.py` from the repository.

**Stage doesn't move**

The EM interface may not be active. Check that the microscope is in
"Remote control" mode and that the GMS EM Control plug-in is loaded.

**Camera acquisition returns zeros**

Verify the camera is inserted and cooled to operating temperature.
Run `gms_configure_detectors(insert_camera=True)` and allow 10–15
minutes for CCD cool-down.
