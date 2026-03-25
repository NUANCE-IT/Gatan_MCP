"""
dm_plugin.py
=============
ZeroMQ bridge plugin that runs **inside** the Gatan Microscopy Suite (GMS)
Python environment, exposing the DigitalMicrograph (DM) Python API to the
GMS-MCP FastMCP server running as a separate process.

Usage (inside the GMS Python console or as a background script)
---------------------------------------------------------------
    exec(open("dm_plugin.py").read())

    # Or import as a module if the path is on sys.path:
    from gms_mcp.dm_plugin import start_bridge, stop_bridge
    start_bridge()   # starts listening in a background thread
    # ... do microscopy work ...
    stop_bridge()    # clean shutdown

Network
-------
    Binds to tcp://0.0.0.0:5555 by default.
    Configurable via environment variable GMS_MCP_ZMQ_PORT.

Security note
-------------
    The ZeroMQ socket is bound to all interfaces (0.0.0.0).
    In a production facility, restrict to the instrument LAN:
        GMS_MCP_ZMQ_BIND=tcp://192.168.1.x:5555
    and configure the firewall to block external access.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import threading
import time
from typing import Any

try:
    import DigitalMicrograph as DM
except ImportError:
    raise RuntimeError(
        "dm_plugin.py must run inside GMS. "
        "Import DigitalMicrograph failed."
    )

try:
    import zmq
except ImportError:
    raise RuntimeError(
        "pyzmq is required. Install it inside the GMS environment:\n"
        "  pip install pyzmq --break-system-packages"
    )

import numpy as np

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_PORT = 5555
_DEFAULT_BIND = f"tcp://0.0.0.0:{_DEFAULT_PORT}"

ZMQ_BIND = os.environ.get("GMS_MCP_ZMQ_BIND", _DEFAULT_BIND)

# ---------------------------------------------------------------------------
# Command dispatcher
# ---------------------------------------------------------------------------

def _to_json_safe(obj: Any) -> Any:
    """Recursively convert numpy types to Python-native JSON-serializable types."""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_json_safe(v) for v in obj]
    return obj


def _image_to_dict(img, include_data: bool = False) -> dict:
    """Serialize a DM Py_Image to a JSON-safe dict."""
    arr = img.GetNumArray()
    tags = img.GetTagGroup()
    ok_exp, exp = tags.GetTagAsFloat("Acquisition:ExposureTime")
    ok_ht, ht   = tags.GetTagAsFloat("Microscope:HighTension_kV")
    ok_mag, mag = tags.GetTagAsFloat("Microscope:Magnification")
    origin, scale, unit = img.GetDimensionCalibration(0, 0)

    result = {
        "name":  img.GetName(),
        "shape": list(arr.shape),
        "dtype": str(arr.dtype),
        "statistics": {
            "min":  float(arr.min()),
            "max":  float(arr.max()),
            "mean": float(arr.mean()),
            "std":  float(arr.std()),
        },
        "calibration": {
            "origin":     float(origin),
            "scale":      float(scale),
            "unit":       unit if isinstance(unit, str) else unit.decode("utf-8", errors="replace"),
        },
        "metadata": {
            "exposure_s":      exp  if ok_exp  else None,
            "high_tension_kV": ht   if ok_ht   else None,
            "magnification":   mag  if ok_mag  else None,
        },
    }
    if include_data:
        result["data_b64"] = base64.b64encode(arr.tobytes()).decode()
        result["data_shape"] = list(arr.shape)
        result["data_dtype"] = str(arr.dtype)
    return result


def _dispatch(cmd: dict) -> dict:
    """
    Route a JSON command to the appropriate DM API call.

    Every handler must return a JSON-serializable dict with at minimum
    {"success": True/False}.
    """
    func   = cmd.get("function", "")
    params = cmd.get("params", {})

    # ── State queries ─────────────────────────────────────────────────────
    if func == "EM_GetState":
        return {
            "success": True,
            "high_tension_V":   DM.EMGetHighTension()   if DM.EMCanGetHighTension()   else None,
            "magnification":    DM.EMGetMagnification() if DM.EMCanGetMagnification() else None,
            "mag_index":        DM.EMGetMagIndex(),
            "spot_size":        DM.EMGetSpotSize(),
            "brightness":       DM.EMGetBrightness(),
            "focus":            DM.EMGetFocus(),
            "operation_mode":   DM.EMGetOperationMode(),
            "illumination_mode":DM.EMGetIlluminationMode(),
            "camera_length_mm": DM.EMGetCameraLength() if DM.EMCanGetCameraLength() else None,
        }

    # ── Stage ──────────────────────────────────────────────────────────────
    if func == "EMGetStagePositions":
        return {
            "success":   True,
            "x_um":      DM.EMGetStageX(),
            "y_um":      DM.EMGetStageY(),
            "z_um":      DM.EMGetStageZ(),
            "alpha_deg": DM.EMGetStageAlpha(),
            "beta_deg":  DM.EMGetStageBeta(),
        }

    if func == "EMSetStagePositions":
        flags = int(params.get("flags", 0))
        DM.EMSetStagePositions(
            flags,
            float(params.get("x",     0.0)),
            float(params.get("y",     0.0)),
            float(params.get("z",     0.0)),
            float(params.get("alpha", 0.0)),
            float(params.get("beta",  0.0)),
        )
        DM.EMWaitUntilReady()
        return {
            "success":   True,
            "x_um":      DM.EMGetStageX(),
            "y_um":      DM.EMGetStageY(),
            "z_um":      DM.EMGetStageZ(),
            "alpha_deg": DM.EMGetStageAlpha(),
            "beta_deg":  DM.EMGetStageBeta(),
        }

    if func == "EMStopStage":
        DM.EMStopStage()
        return {"success": True}

    # ── Optics ─────────────────────────────────────────────────────────────
    if func == "EMSetSpotSize":
        DM.EMSetSpotSize(int(params["spot_size"]))
        return {"success": True, "spot_size": DM.EMGetSpotSize()}

    if func == "EMSetFocus":
        DM.EMSetFocus(float(params["focus"]))
        return {"success": True, "focus": DM.EMGetFocus()}

    if func == "EMChangeFocus":
        DM.EMChangeFocus(float(params["delta"]))
        return {"success": True, "focus": DM.EMGetFocus()}

    if func == "EMSetCalibratedBeamShift":
        DM.EMSetCalibratedBeamShift(float(params["x"]), float(params["y"]))
        return {"success": True}

    if func == "EMSetBeamTilt":
        DM.EMSetBeamTilt(float(params["x"]), float(params["y"]))
        return {"success": True}

    if func == "EMSetObjectiveStigmation":
        DM.EMSetObjectiveStigmation(float(params["x"]), float(params["y"]))
        return {"success": True}

    if func == "EMSetCameraLength":
        DM.EMSetCameraLength(float(params["camera_length_mm"]))
        return {
            "success": True,
            "camera_length_mm": DM.EMGetCameraLength() if DM.EMCanGetCameraLength() else None,
        }

    # ── Camera / CCD ───────────────────────────────────────────────────────
    if func == "CM_GetCameraInfo":
        cam = DM.CM_GetCurrentCamera()
        return {
            "success":    True,
            "name":       DM.CM_GetCameraName(cam),
            "identifier": DM.CM_GetCameraIdentifier(cam),
            "inserted":   DM.CM_GetCameraInserted(cam),
            "temp_c":     DM.CM_GetActualTemperature_C(cam),
        }

    if func == "CM_SetCameraInserted":
        cam = DM.CM_GetCurrentCamera()
        DM.CM_SetCameraInserted(cam, int(params["inserted"]))
        return {"success": True, "inserted": DM.CM_GetCameraInserted(cam)}

    if func == "CM_SetTargetTemperature":
        cam = DM.CM_GetCurrentCamera()
        DM.CM_SetTargetTemperature_C(cam, 1, float(params["temp_c"]))
        return {"success": True}

    if func == "CM_AcquireImage":
        cam = DM.CM_GetCurrentCamera()
        acq = DM.CM_CreateAcquisitionParameters_FullCCD(
            cam,
            int(params.get("processing", 3)),
            float(params.get("exposure", 1.0)),
            int(params.get("binning", 1)),
            int(params.get("binning", 1)),
        )
        if "roi" in params:
            DM.CM_SetCCDReadArea(acq, *[int(v) for v in params["roi"]])
        DM.CM_Validate_AcquisitionParameters(cam, acq)
        img = DM.CM_AcquireImage(cam, acq)
        img.SetName(params.get("name", "MCP_Acquisition"))
        img.ShowImage()
        return {"success": True, **_image_to_dict(img, params.get("include_data", False))}

    # ── DigiScan / STEM ────────────────────────────────────────────────────
    if func == "DS_Configure":
        DM.DSSetFrameSize(int(params.get("width", 512)), int(params.get("height", 512)))
        DM.DSSetPixelTime(float(params.get("dwell_us", 10.0)))
        DM.DSSetRotation(float(params.get("rotation_deg", 0.0)))
        if "flyback_us" in params:
            DM.DSSetFlybackTime(float(params["flyback_us"]))
        n = DM.DSGetNumberOfSignals()
        enabled = params.get("signals", [0, 1])
        for ch in range(n):
            DM.DSSetSignalEnabled(ch, 1 if ch in enabled else 0)
        return {"success": True}

    if func == "DS_Acquire":
        DM.DSStartAcquisition()
        DM.DSWaitUntilFinished()
        img = DM.GetFrontImage()
        return {"success": True, **_image_to_dict(img, params.get("include_data", False))}

    # ── GIF / EELS ─────────────────────────────────────────────────────────
    if func == "EELS_Configure":
        DM.IFSetEELSMode()
        DM.IFCSetEnergy(float(params.get("energy_offset_eV", 0.0)))
        DM.IFCSetActiveDispersions(int(params.get("dispersion_idx", 0)))
        slit_w = float(params.get("slit_width_eV", 10.0))
        if slit_w > 0:
            DM.IFCSetSlitWidth(slit_w)
            DM.IFCSetSlitIn(1)
        else:
            DM.IFCSetSlitIn(0)
        return {
            "success":          True,
            "energy_loss_eV":   DM.IFGetEnergyLoss(0),
            "slit_width_eV":    DM.IFCGetSlitWidth(),
            "in_eels_mode":     DM.IFIsInEELSMode(),
        }

    if func == "EELS_Acquire":
        cam = DM.CM_GetCurrentCamera()
        acq = DM.CM_CreateAcquisitionParameters_FullCCD(
            cam, 3, float(params.get("exposure", 1.0)), 1, 1
        )
        if params.get("full_vertical_binning", True):
            DM.CM_SetBinning(acq, 1, 2048)
        DM.CM_Validate_AcquisitionParameters(cam, acq)
        spec = DM.CM_AcquireImage(cam, acq)
        spec.SetName("EELS_Spectrum")
        spec.ShowImage()
        return {"success": True, **_image_to_dict(spec, params.get("include_data", False))}

    if func == "IFSetImageMode":
        DM.IFSetImageMode()
        return {"success": True, "in_image_mode": DM.IFIsInImageMode()}

    # ── Utility ────────────────────────────────────────────────────────────
    if func == "GetFrontImage":
        img = DM.GetFrontImage()
        return {"success": True, **_image_to_dict(img, params.get("include_data", False))}

    if func == "SaveImage":
        img = DM.GetFrontImage()
        path = params.get("path", "C:\\MCP_Export\\image.dm4")
        DM.SaveImage(img, path)
        return {"success": True, "path": path}

    if func == "Ping":
        return {"success": True, "message": "GMS DM bridge alive", "time": time.time()}

    # ── Unknown ────────────────────────────────────────────────────────────
    return {
        "success": False,
        "error":   f"Unknown function: {func!r}",
        "hint":    "Check gms_mcp.dm_plugin._dispatch for supported commands.",
    }


# ---------------------------------------------------------------------------
# Bridge thread
# ---------------------------------------------------------------------------

_zmq_context: zmq.Context | None = None
_zmq_socket: zmq.Socket | None   = None
_bridge_thread: threading.Thread | None = None
_running = threading.Event()


def _bridge_loop() -> None:
    """Main ZeroMQ REP loop — runs in a daemon thread."""
    global _zmq_context, _zmq_socket

    _zmq_context = zmq.Context()
    _zmq_socket  = _zmq_context.socket(zmq.REP)
    _zmq_socket.bind(ZMQ_BIND)
    _zmq_socket.setsockopt(zmq.RCVTIMEO, 500)   # 500 ms poll timeout

    DM.Result(f"[GMS-MCP] DM bridge ready on {ZMQ_BIND}\n")

    while _running.is_set():
        try:
            msg_bytes = _zmq_socket.recv()
        except zmq.Again:
            # Timeout — check _running flag and loop
            DM.DoEvents()
            continue
        except zmq.ZMQError:
            break

        try:
            cmd    = json.loads(msg_bytes.decode("utf-8"))
            result = _dispatch(cmd)
            result = _to_json_safe(result)
        except Exception as exc:
            result = {"success": False, "error": str(exc)}

        try:
            _zmq_socket.send(json.dumps(result).encode("utf-8"))
        except zmq.ZMQError:
            break

        DM.DoEvents()   # keep GMS UI responsive during long acquisitions

    _zmq_socket.close()
    _zmq_context.term()
    DM.Result("[GMS-MCP] DM bridge stopped.\n")


def start_bridge(bind: str = ZMQ_BIND) -> None:
    """Start the ZeroMQ bridge in a background daemon thread."""
    global _bridge_thread, ZMQ_BIND

    if _running.is_set():
        DM.Result("[GMS-MCP] Bridge is already running.\n")
        return

    ZMQ_BIND = bind
    _running.set()
    _bridge_thread = threading.Thread(target=_bridge_loop, daemon=True, name="gms-mcp-bridge")
    _bridge_thread.start()
    DM.Result(f"[GMS-MCP] Bridge thread started → {bind}\n")


def stop_bridge() -> None:
    """Signal the bridge thread to stop and wait for it to exit."""
    _running.clear()
    if _bridge_thread and _bridge_thread.is_alive():
        _bridge_thread.join(timeout=3.0)
    DM.Result("[GMS-MCP] Bridge stopped.\n")


# ---------------------------------------------------------------------------
# Auto-start when exec()'d inside GMS
# ---------------------------------------------------------------------------

if __name__ == "__main__" or "DigitalMicrograph" in sys.modules:
    start_bridge()
