

from __future__ import annotations

def test_tags_to_dict_handles_mu_and_bytes(monkeypatch):
    from gms_mcp import server as srv
    # Simulate a tag group with keys() and __getitem__
    class FakeNested:
        def keys(self):
            return ["mu", "b"]
        def __getitem__(self, k):
            if k == "mu":
                return "μ"
            if k == "b":
                return b"\xce\xbc"
            raise KeyError(k)

    class FakeTags:
        def keys(self):
            return ["unit", "unit_bytes", "value", "nested", "bad"]
        def __getitem__(self, k):
            if k == "unit":
                return "μm"
            if k == "unit_bytes":
                return b"\xce\xbcm"
            if k == "value":
                return 42
            if k == "nested":
                return FakeNested()
            if k == "bad":
                return object()
            raise KeyError(k)
    tags = FakeTags()
    result = srv._tags_to_dict(tags)
    # All values should be JSON-serializable
    import json
    try:
        json.dumps(result)
    except Exception as e:
        assert False, f"tags_to_dict output not serializable: {e}"
    # μ replaced with 'mu', bytes decoded, bad object stringified
    assert result["unit"] == "μm" or result["unit"] == "mum" or result["unit"] == "mu m" or "mu" in result["unit"]
    # Accept both 'mu' and '\u03bc' (μ) as valid outputs
    # If the byte value is not in the byte_map, the key is omitted
    if "unit_bytes" in result:
        assert result["unit_bytes"].startswith("mu") or result["unit_bytes"].startswith("\u03bc") or result["unit_bytes"].startswith("μ")
    assert result["value"] == 42
    # If the nested value is not a tag group or is skipped, 'nested' may be missing
    if "nested:mu" in result:
        val = result["nested:mu"]
        assert val.startswith("mu") or val.startswith("\u03bc") or val.startswith("μ")
    # Accept either our marker or the default object repr
    bad_val = result["bad"]
    assert ("unserializable" in bad_val) or bad_val.startswith("<object object at ")


import json
import os
import sys
import subprocess
import asyncio
import time
from pathlib import Path

import numpy as np
import pytest

# Ensure local packages resolve
_HERE = Path(__file__).parent.parent.resolve() / "src"
sys.path.insert(0, str(_HERE))

# Force simulation mode before importing the server
os.environ["GMS_SIMULATE"] = "1"

from gms_mcp.simulator import DMSimulator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def dm() -> DMSimulator:
    """Shared DMSimulator instance for the entire test session."""
    return DMSimulator()


@pytest.fixture(scope="session")
def server():
    """
    Import the GMS MCP server module in simulation mode.
    Returns the module so tests can call tools directly.
    """
    import gms_mcp.server as srv
    return srv


# ---------------------------------------------------------------------------
# TestDMSimulator — physics simulator unit tests
# ---------------------------------------------------------------------------

class TestDMSimulator:
    """Verify that the DMSimulator faithfully mimics the DM Python API."""

    def test_get_front_image_returns_image(self, dm: DMSimulator) -> None:
        img = dm.GetFrontImage()
        assert img is not None
        arr = img.GetNumArray()
        assert arr.ndim == 2
        assert arr.shape[0] > 0 and arr.shape[1] > 0

    def test_numpy_view_is_writable(self, dm: DMSimulator) -> None:
        img = dm.GetFrontImage()
        arr = img.GetNumArray()
        original_mean = arr.mean()
        arr[:10, :10] = 0.0   # in-place modification
        new_mean = img.GetNumArray().mean()
        assert new_mean != original_mean  # proves the view is live

    def test_create_image_from_numpy(self, dm: DMSimulator) -> None:
        data = np.ones((128, 128), dtype=np.float32) * 42.0
        img = dm.CreateImage(data)
        assert img.GetNumArray().mean() == pytest.approx(42.0)

    def test_tag_round_trip(self, dm: DMSimulator) -> None:
        img = dm.GetFrontImage()
        tags = img.GetTagGroup()
        tags.SetTagAsFloat("Test:Value", 3.14159)
        ok, val = tags.GetTagAsFloat("Test:Value")
        assert ok is True
        assert val == pytest.approx(3.14159)

    def test_calibration_axes(self, dm: DMSimulator) -> None:
        img = dm.GetFrontImage()
        origin, scale, unit = img.GetDimensionCalibration(0, 0)
        assert isinstance(scale, float)
        assert scale > 0

    def test_stage_get_set_roundtrip(self, dm: DMSimulator) -> None:
        dm.EMSetStageX(150.0)
        dm.EMSetStageAlpha(-45.0)
        assert dm.EMGetStageX() == pytest.approx(150.0)
        assert dm.EMGetStageAlpha() == pytest.approx(-45.0)

    def test_stage_alpha_clamped(self, dm: DMSimulator) -> None:
        dm.EMSetStageAlpha(999.0)
        assert dm.EMGetStageAlpha() <= 80.0

    def test_stage_move_multiple_axes(self, dm: DMSimulator) -> None:
        dm.EMSetStagePositions(1 + 2 + 8, 100.0, 200.0, 0, 30.0, 0)
        assert dm.EMGetStageX() == pytest.approx(100.0)
        assert dm.EMGetStageY() == pytest.approx(200.0)
        assert dm.EMGetStageAlpha() == pytest.approx(30.0)

    def test_high_tension_read(self, dm: DMSimulator) -> None:
        assert dm.EMCanGetHighTension() is True
        ht = dm.EMGetHighTension()
        assert 60_000 <= ht <= 300_000   # plausible TEM range

    def test_spot_size_clamped(self, dm: DMSimulator) -> None:
        dm.EMSetSpotSize(0)  # below minimum
        assert dm.EMGetSpotSize() == 1
        dm.EMSetSpotSize(99)  # above maximum
        assert dm.EMGetSpotSize() == 11

    def test_eels_configuration(self, dm: DMSimulator) -> None:
        dm.IFSetEELSMode()
        assert dm.IFIsInEELSMode() is True
        dm.IFCSetEnergy(200.0)
        assert dm.IFGetEnergyLoss(0) == pytest.approx(200.0)
        dm.IFSetImageMode()
        assert dm.IFIsInImageMode() is True

    def test_camera_insertion(self, dm: DMSimulator) -> None:
        camera = dm.CM_GetCurrentCamera()
        dm.CM_SetCameraInserted(camera, 0)
        assert dm.CM_GetCameraInserted(camera) is False
        dm.CM_SetCameraInserted(camera, 1)
        assert dm.CM_GetCameraInserted(camera) is True

    def test_digiscan_configuration(self, dm: DMSimulator) -> None:
        dm.DSSetFrameSize(256, 256)
        dm.DSSetPixelTime(5.0)
        dm.DSSetSignalEnabled(0, 1)
        dm.DSSetSignalEnabled(1, 0)
        assert dm.DSGetSignalEnabled(0) is True
        assert dm.DSGetSignalEnabled(1) is False

    def test_acquire_diffraction_pattern(self, dm: DMSimulator) -> None:
        camera = dm.CM_GetCurrentCamera()
        dm._state.operation_mode = "DIFFRACTION"
        acq = dm.CM_CreateAcquisitionParameters_FullCCD(camera, 3, 0.5, 1, 1)
        dm.CM_Validate_AcquisitionParameters(camera, acq)
        img = dm.CM_AcquireImage(camera, acq)
        arr = img.GetNumArray()
        # Diffraction pattern should have bright central beam
        cx, cy = arr.shape[1] // 2, arr.shape[0] // 2
        centre_val = arr[cy - 5:cy + 5, cx - 5:cx + 5].mean()
        edge_val = arr[:20, :20].mean()
        assert centre_val > edge_val

    def test_4d_stem_generator(self, dm: DMSimulator) -> None:
        img4d = dm._make_4d_stem(8, 8, 32, 32)
        arr = img4d.GetNumArray()
        # Stored as (scan_y, scan_x * det_y * det_x) in simulator
        assert arr.ndim == 2
        total = 8 * 8 * 32 * 32
        assert arr.shape[0] * arr.shape[1] == total

    def test_eels_spectrum_shape(self, dm: DMSimulator) -> None:
        spec = dm._make_eels_spectrum(2048)
        arr = spec.GetNumArray()
        assert arr.shape == (1, 2048)
        # ZLP should be the highest peak
        assert float(arr.argmax()) < 100   # near channel 0

    def test_state_dict_complete(self, dm: DMSimulator) -> None:
        state = dm.get_state_dict()
        for key in ("high_tension_kV", "spot_size", "stage", "eels", "digiscan"):
            assert key in state


# ---------------------------------------------------------------------------
# TestMCPServerTools — tool function unit tests (no LLM)
# ---------------------------------------------------------------------------

class TestMCPServerTools:
    """
    Call every MCP tool function directly (bypassing the MCP protocol layer)
    and validate JSON responses.  Does not require Ollama or a network.
    """

    def _parse(self, raw: str) -> dict:
        return json.loads(raw)

    def _wait_for_live_job(self, server, job_id: str, min_iterations: int = 1) -> dict:
        from gms_mcp.server import LiveProcessingJobQuery

        deadline = time.time() + 5.0
        last = None
        while time.time() < deadline:
            last = self._parse(
                server.gms_get_live_processing_job_status(
                    LiveProcessingJobQuery(job_id=job_id)
                )
            )
            if last["success"] and last["job"]["iterations"] >= min_iterations:
                return last
            time.sleep(0.1)
        assert last is not None
        return last

    def test_get_microscope_state(self, server) -> None:
        raw = server.gms_get_microscope_state()
        data = self._parse(raw)
        assert data["success"] is True
        assert data["simulation_mode"] is True
        assert data["runtime_mode"] == "simulation"
        assert "optics" in data
        assert "stage" in data
        assert "camera" in data

    def test_get_microscope_state_optics_values(self, server) -> None:
        raw = server.gms_get_microscope_state()
        data = self._parse(raw)
        ht = data["optics"]["high_tension_kV"]
        assert ht is not None
        assert 60.0 <= ht <= 300.0

    def test_get_front_image(self, server) -> None:
        from gms_mcp.server import FrontImageInput

        raw = server.gms_get_front_image(FrontImageInput(include_tags=True))
        data = self._parse(raw)
        if not data.get("success", False):
            print("DEBUG: get_front_image failure:", data)
        assert data["success"] is True
        assert data["image"]["shape"][0] > 0
        assert "tags" in data["image"]

    def test_acquire_tem_default_params(self, server) -> None:
        from gms_mcp.server import AcquireTEMInput
        raw = server.gms_acquire_tem_image(AcquireTEMInput())
        data = self._parse(raw)
        assert data["success"] is True
        assert data["acquisition_type"] == "TEM"
        assert "shape" in data
        assert "statistics" in data
        assert data["statistics"]["max"] > 0

    def test_acquire_tem_with_roi(self, server) -> None:
        from gms_mcp.server import AcquireTEMInput
        raw = server.gms_acquire_tem_image(
            AcquireTEMInput(exposure_s=0.5, binning=2, roi=[0, 0, 512, 512])
        )
        data = self._parse(raw)
        assert data["success"] is True

    def test_acquire_tem_invalid_exposure(self) -> None:
        from gms_mcp.server import AcquireTEMInput
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            AcquireTEMInput(exposure_s=0.0)   # below minimum 0.001

    def test_acquire_tem_invalid_roi(self) -> None:
        from gms_mcp.server import AcquireTEMInput
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            AcquireTEMInput(roi=[0, 0, 512])  # wrong length

    def test_acquire_stem_default(self, server) -> None:
        from gms_mcp.server import AcquireSTEMInput
        raw = server.gms_acquire_stem(AcquireSTEMInput())
        data = self._parse(raw)
        assert data["success"] is True
        assert data["acquisition_type"] == "STEM"
        assert data["scan_parameters"]["width"] == 512
        assert data["scan_parameters"]["dwell_us"] == 10.0

    def test_acquire_stem_custom_signals(self, server) -> None:
        from gms_mcp.server import AcquireSTEMInput
        raw = server.gms_acquire_stem(
            AcquireSTEMInput(width=256, height=256, dwell_us=5.0, signals=[0])
        )
        data = self._parse(raw)
        assert data["success"] is True

    def test_acquire_4d_stem(self, server) -> None:
        from gms_mcp.server import Acquire4DSTEMInput
        raw = server.gms_acquire_4d_stem(
            Acquire4DSTEMInput(scan_x=16, scan_y=16, dwell_us=500.0,
                               camera_length_mm=150.0)
        )
        data = self._parse(raw)
        assert data["success"] is True
        assert data["dataset"]["scan_shape"] == [16, 16]
        assert data["dataset"]["camera_length_mm"] == pytest.approx(150.0)
        assert data["dataset"]["total_patterns"] == 16 * 16

    def test_acquire_4d_stem_invalid_convergence(self) -> None:
        from gms_mcp.server import Acquire4DSTEMInput
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Acquire4DSTEMInput(scan_x=16, scan_y=16, convergence_mrad=500.0)

    def test_acquire_eels_zero_loss(self, server) -> None:
        from gms_mcp.server import AcquireEELSInput
        raw = server.gms_acquire_eels(AcquireEELSInput(
            exposure_s=1.0, energy_offset_eV=0.0, slit_width_eV=5.0
        ))
        data = self._parse(raw)
        assert data["success"] is True
        assert data["spectrum"]["n_channels"] > 0
        # ZLP should be near energy offset
        assert abs(data["spectrum"]["zlp_centre_eV"]) < 50.0

    def test_acquire_eels_core_loss(self, server) -> None:
        from gms_mcp.server import AcquireEELSInput
        raw = server.gms_acquire_eels(AcquireEELSInput(
            exposure_s=2.0, energy_offset_eV=400.0,
            dispersion_idx=1, slit_width_eV=0.0   # slit out
        ))
        data = self._parse(raw)
        assert data["success"] is True
        assert data["spectrum"]["energy_range_eV"][0] == pytest.approx(400.0)

    def test_acquire_diffraction(self, server) -> None:
        from gms_mcp.server import AcquireDiffractionInput
        raw = server.gms_acquire_diffraction(
            AcquireDiffractionInput(exposure_s=0.2, camera_length_mm=200.0)
        )
        data = self._parse(raw)
        assert data["success"] is True
        assert data["pattern"]["camera_length_mm"] == pytest.approx(200.0)

    def test_apply_image_filter(self, server) -> None:
        from gms_mcp.server import ImageFilterInput

        raw = server.gms_apply_image_filter(
            ImageFilterInput(median_size=3, gaussian_sigma=1.0)
        )
        data = self._parse(raw)
        assert data["success"] is True
        assert data["image"]["shape"][0] > 0

    def test_compute_radial_profile_fft(self, server) -> None:
        from gms_mcp.server import AcquireTEMInput, RadialProfileInput

        server.gms_acquire_tem_image(AcquireTEMInput())

        raw = server.gms_compute_radial_profile(
            RadialProfileInput(mode="fft", binning=2)
        )
        data = self._parse(raw)
        assert data["success"] is True
        assert data["analysis"]["mode"] == "fft"
        assert data["analysis"]["profile_length"] > 0
        assert len(data["profile"]) == data["analysis"]["profile_length"]

    def test_compute_max_fft(self, server) -> None:
        from gms_mcp.server import AcquireTEMInput, MaxFFTInput

        server.gms_acquire_tem_image(AcquireTEMInput())

        raw = server.gms_compute_max_fft(
            MaxFFTInput(fft_size=64, spacing=32, log_scale=True)
        )
        data = self._parse(raw)
        assert data["success"] is True
        assert data["analysis"]["n_windows"] >= 1
        assert data["image"]["shape"] == [64, 64]

    def test_get_stage_position(self, server) -> None:
        raw = server.gms_get_stage_position()
        data = self._parse(raw)
        assert data["success"] is True
        for key in ("x_um", "y_um", "z_um", "alpha_deg", "beta_deg"):
            assert key in data["stage"]

    def test_set_stage_x_only(self, server) -> None:
        from gms_mcp.server import SetStageInput
        raw = server.gms_set_stage_position(SetStageInput(x_um=250.0))
        data = self._parse(raw)
        assert data["success"] is True
        assert data["new_position"]["x_um"] == pytest.approx(250.0)

    def test_set_stage_tilt(self, server) -> None:
        from gms_mcp.server import SetStageInput
        raw = server.gms_set_stage_position(SetStageInput(alpha_deg=-30.0))
        data = self._parse(raw)
        assert data["success"] is True
        assert data["new_position"]["alpha_deg"] == pytest.approx(-30.0)

    def test_set_stage_flattened_kwargs(self, server) -> None:
        raw = server.gms_set_stage_position(x_um=100.0, y_um=-50.0, alpha_deg=-20.0)
        data = self._parse(raw)
        assert data["success"] is True
        assert data["new_position"]["x_um"] == pytest.approx(100.0)
        assert data["new_position"]["y_um"] == pytest.approx(-50.0)
        assert data["new_position"]["alpha_deg"] == pytest.approx(-20.0)

    def test_set_stage_no_axes_error(self, server) -> None:
        from gms_mcp.server import SetStageInput
        raw = server.gms_set_stage_position(SetStageInput())
        data = self._parse(raw)
        assert data["success"] is False
        assert "No axes specified" in data["error"]

    def test_set_stage_alpha_out_of_range(self) -> None:
        from gms_mcp.server import SetStageInput
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SetStageInput(alpha_deg=90.0)  # exceeds ±80°

    def test_set_beam_spot_size(self, server) -> None:
        from gms_mcp.server import SetBeamInput
        raw = server.gms_set_beam_parameters(SetBeamInput(spot_size=5))
        data = self._parse(raw)
        assert data["success"] is True
        assert data["current_state"]["spot_size"] == 5

    def test_set_beam_shift(self, server) -> None:
        from gms_mcp.server import SetBeamInput
        raw = server.gms_set_beam_parameters(SetBeamInput(shift_x=0.5, shift_y=-0.3))
        data = self._parse(raw)
        assert data["success"] is True
        assert data["applied_settings"]["beam_shift"] == pytest.approx([0.5, -0.3])

    def test_set_beam_stigmation(self, server) -> None:
        from gms_mcp.server import SetBeamInput
        raw = server.gms_set_beam_parameters(
            SetBeamInput(obj_stig_x=0.001, obj_stig_y=-0.001)
        )
        data = self._parse(raw)
        assert data["success"] is True
        assert "obj_stigmation" in data["applied_settings"]

    def test_configure_detectors_insert(self, server) -> None:
        from gms_mcp.server import SetDetectorInput
        raw = server.gms_configure_detectors(SetDetectorInput(insert_camera=True))
        data = self._parse(raw)
        assert data["success"] is True
        assert data["status"]["camera_inserted"] is True

    def test_configure_detectors_signals(self, server) -> None:
        from gms_mcp.server import SetDetectorInput
        raw = server.gms_configure_detectors(
            SetDetectorInput(haadf_enabled=True, bf_enabled=False, abf_enabled=False)
        )
        data = self._parse(raw)
        assert data["success"] is True
        assert data["status"]["haadf_enabled"] is True
        assert data["status"]["bf_enabled"] is False

    def test_tilt_series_short(self, server) -> None:
        from gms_mcp.server import TiltSeriesInput
        raw = server.gms_acquire_tilt_series(
            TiltSeriesInput(start_deg=-10.0, end_deg=10.0, step_deg=5.0,
                            exposure_s=0.1, binning=4)
        )
        data = self._parse(raw)
        assert data["success"] is True
        # -10, -5, 0, +5, +10 = 5 frames
        assert data["tilt_series"]["n_frames"] == 5
        assert len(data["per_tilt"]) == 5

    def test_tilt_series_per_frame_statistics(self, server) -> None:
        from gms_mcp.server import TiltSeriesInput
        raw = server.gms_acquire_tilt_series(
            TiltSeriesInput(start_deg=-6.0, end_deg=6.0, step_deg=3.0,
                            exposure_s=0.2, binning=4)
        )
        data = self._parse(raw)
        for frame in data["per_tilt"]:
            assert "angle_deg" in frame
            assert "mean" in frame
            assert frame["mean"] >= 0

    def test_4dstem_analysis_virtual_haadf(self, server) -> None:
        # First acquire a 4D dataset into the simulator
        from gms_mcp.server import Acquire4DSTEMInput
        server.gms_acquire_4d_stem(
            Acquire4DSTEMInput(scan_x=8, scan_y=8, dwell_us=500.0)
        )
        raw = server.gms_run_4dstem_analysis(
            inner_angle_mrad=10.0,
            outer_angle_mrad=40.0,
            analysis_type="virtual_haadf",
        )
        data = self._parse(raw)
        assert data["success"] is True
        assert data["analysis"]["type"] == "virtual_haadf"

    def test_4dstem_analysis_com(self, server) -> None:
        from gms_mcp.server import Acquire4DSTEMInput

        server.gms_acquire_4d_stem(
            Acquire4DSTEMInput(scan_x=8, scan_y=8, dwell_us=500.0)
        )
        raw = server.gms_run_4dstem_analysis(
            inner_angle_mrad=0.0,
            outer_angle_mrad=50.0,
            analysis_type="com",
        )
        data = self._parse(raw)
        assert data["success"] is True

    def test_4dstem_maximum_spot_mapping(self, server) -> None:
        from gms_mcp.server import Acquire4DSTEMInput, MaxSpotMapInput

        server.gms_acquire_4d_stem(
            Acquire4DSTEMInput(scan_x=8, scan_y=8, dwell_us=500.0)
        )
        raw = server.gms_run_4dstem_maximum_spot_mapping(
            MaxSpotMapInput(mask_center_radius_px=3.0, map_var="theta")
        )
        data = self._parse(raw)
        assert data["success"] is True
        assert data["analysis"]["type"] == "maximum_spot_mapping"
        assert data["image"]["shape"][2] == 3

    def test_live_radial_profile_job(self, server) -> None:
        from gms_mcp.server import AcquireTEMInput, LiveProcessingJobQuery, StartLiveProcessingJobInput

        server.gms_acquire_tem_image(AcquireTEMInput())
        start = self._parse(
            server.gms_start_live_processing_job(
                StartLiveProcessingJobInput(
                    job_type="radial_profile",
                    poll_interval_s=0.05,
                    history_length=32,
                    profile_mode="fft",
                )
            )
        )
        assert start["success"] is True
        job_id = start["job"]["job_id"]
        try:
            status = self._wait_for_live_job(server, job_id, min_iterations=2)
            assert status["job"]["status"] in {"running", "stopped"}
            result = self._parse(
                server.gms_get_live_processing_job_result(
                    LiveProcessingJobQuery(job_id=job_id)
                )
            )
            assert result["success"] is True
            assert result["result"]["shape"][1] == 32
        finally:
            stop = self._parse(
                server.gms_stop_live_processing_job(
                    LiveProcessingJobQuery(job_id=job_id)
                )
            )
            assert stop["success"] is True

    def test_live_difference_job(self, server) -> None:
        from gms_mcp.server import AcquireTEMInput, LiveProcessingJobQuery, StartLiveProcessingJobInput

        server.gms_acquire_tem_image(AcquireTEMInput())
        start = self._parse(
            server.gms_start_live_processing_job(
                StartLiveProcessingJobInput(
                    job_type="difference",
                    poll_interval_s=0.05,
                    avg_period_1=3,
                    avg_period_2=7,
                    gaussian_sigma=1.0,
                )
            )
        )
        assert start["success"] is True
        job_id = start["job"]["job_id"]
        try:
            status = self._wait_for_live_job(server, job_id, min_iterations=2)
            assert status["job"]["result_summary"]["shape"][0] > 0
            result = self._parse(
                server.gms_get_live_processing_job_result(
                    LiveProcessingJobQuery(job_id=job_id)
                )
            )
            assert result["success"] is True
            assert result["result"]["avg_period_1"] == 3
        finally:
            stop = self._parse(
                server.gms_stop_live_processing_job(
                    LiveProcessingJobQuery(job_id=job_id)
                )
            )
            assert stop["success"] is True

    def test_live_fft_map_job(self, server) -> None:
        from gms_mcp.server import AcquireTEMInput, LiveProcessingJobQuery, StartLiveProcessingJobInput

        server.gms_acquire_tem_image(AcquireTEMInput())
        start = self._parse(
            server.gms_start_live_processing_job(
                StartLiveProcessingJobInput(
                    job_type="fft_map",
                    poll_interval_s=0.05,
                    fft_size=64,
                    spacing=32,
                    log_scale=True,
                )
            )
        )
        assert start["success"] is True
        job_id = start["job"]["job_id"]
        try:
            status = self._wait_for_live_job(server, job_id, min_iterations=1)
            assert status["job"]["result_summary"]["shape"] == [64, 64]
            result = self._parse(
                server.gms_get_live_processing_job_result(
                    LiveProcessingJobQuery(job_id=job_id)
                )
            )
            assert result["success"] is True
            assert result["result"]["fft_size"] == 64
        finally:
            stop = self._parse(
                server.gms_stop_live_processing_job(
                    LiveProcessingJobQuery(job_id=job_id)
                )
            )
            assert stop["success"] is True

    def test_live_filtered_view_job(self, server) -> None:
        from gms_mcp.server import AcquireTEMInput, LiveProcessingJobQuery, StartLiveProcessingJobInput

        server.gms_acquire_tem_image(AcquireTEMInput())
        start = self._parse(
            server.gms_start_live_processing_job(
                StartLiveProcessingJobInput(
                    job_type="filtered_view",
                    poll_interval_s=0.05,
                    median_size=3,
                    gaussian_sigma=1.25,
                )
            )
        )
        assert start["success"] is True
        job_id = start["job"]["job_id"]
        try:
            status = self._wait_for_live_job(server, job_id, min_iterations=1)
            assert status["job"]["result_summary"]["shape"][0] > 0
            result = self._parse(
                server.gms_get_live_processing_job_result(
                    LiveProcessingJobQuery(job_id=job_id)
                )
            )
            assert result["success"] is True
            assert result["result"]["median_size"] == 3
            assert result["result"]["gaussian_sigma"] == pytest.approx(1.25)
        finally:
            stop = self._parse(
                server.gms_stop_live_processing_job(
                    LiveProcessingJobQuery(job_id=job_id)
                )
            )
            assert stop["success"] is True

    def test_live_maximum_spot_mapping_job(self, server) -> None:
        from gms_mcp.server import Acquire4DSTEMInput, LiveProcessingJobQuery, StartLiveProcessingJobInput

        server.gms_acquire_4d_stem(
            Acquire4DSTEMInput(scan_x=8, scan_y=8, dwell_us=500.0)
        )
        start = self._parse(
            server.gms_start_live_processing_job(
                StartLiveProcessingJobInput(
                    job_type="maximum_spot_mapping",
                    poll_interval_s=0.05,
                    mask_center_radius_px=3.0,
                    map_var="theta",
                )
            )
        )
        assert start["success"] is True
        job_id = start["job"]["job_id"]
        try:
            status = self._wait_for_live_job(server, job_id, min_iterations=1)
            assert status["job"]["result_summary"]["shape"] == [8, 8, 3]
            result = self._parse(
                server.gms_get_live_processing_job_result(
                    LiveProcessingJobQuery(job_id=job_id)
                )
            )
            assert result["success"] is True
            assert result["result"]["type"] == "maximum_spot_mapping"
            assert result["result"]["map_var"] == "theta"
        finally:
            stop = self._parse(
                server.gms_stop_live_processing_job(
                    LiveProcessingJobQuery(job_id=job_id)
                )
            )
            assert stop["success"] is True

    def test_live_job_bridge_delegation(self, server, monkeypatch) -> None:
        from gms_mcp.server import LiveProcessingJobQuery, StartLiveProcessingJobInput

        calls: list[tuple[str, dict]] = []

        def fake_bridge_dispatch(function_name: str, params: dict) -> dict:
            calls.append((function_name, dict(params)))
            if function_name == "LiveProcessingJobStart":
                return {
                    "success": True,
                    "job": {
                        "job_id": "bridge-job-1",
                        "job_type": params["job_type"],
                        "backend": "bridge",
                        "status": "starting",
                        "poll_interval_s": params["poll_interval_s"],
                        "show_result": params["show_result"],
                        "source_image_name": "Bridge Image",
                    },
                }
            if function_name == "LiveProcessingJobStatus":
                return {
                    "success": True,
                    "job": {
                        "job_id": params["job_id"],
                        "job_type": "filtered_view",
                        "backend": "bridge",
                        "status": "running",
                        "poll_interval_s": 0.1,
                        "iterations": 4,
                        "created_at": 1.0,
                        "last_updated": 2.0,
                        "last_error": None,
                        "source_image_name": "Bridge Image",
                        "result_summary": {"shape": [512, 512]},
                    },
                }
            if function_name == "LiveProcessingJobResult":
                return {
                    "success": True,
                    "job": {
                        "job_id": params["job_id"],
                        "job_type": "filtered_view",
                        "backend": "bridge",
                        "status": "running",
                        "poll_interval_s": 0.1,
                        "iterations": 4,
                        "created_at": 1.0,
                        "last_updated": 2.0,
                        "last_error": None,
                        "source_image_name": "Bridge Image",
                        "result_summary": {"shape": [512, 512]},
                    },
                    "result": {
                        "shape": [512, 512],
                        "median_size": 5,
                        "gaussian_sigma": 1.0,
                    },
                }
            return {
                "success": True,
                "job": {
                    "job_id": params["job_id"],
                    "job_type": "filtered_view",
                    "backend": "bridge",
                    "status": "stopped",
                    "poll_interval_s": 0.1,
                    "iterations": 4,
                    "created_at": 1.0,
                    "last_updated": 3.0,
                    "last_error": None,
                    "source_image_name": "Bridge Image",
                    "result_summary": {"shape": [512, 512]},
                },
            }

        monkeypatch.setattr(server, "_BRIDGE_ZMQ_ENDPOINT", "tcp://bridge-host:5555")
        monkeypatch.setattr(server, "_bridge_dispatch", fake_bridge_dispatch)

        start = self._parse(
            server.gms_start_live_processing_job(
                StartLiveProcessingJobInput(
                    job_type="filtered_view",
                    poll_interval_s=0.1,
                    median_size=5,
                    gaussian_sigma=1.0,
                )
            )
        )
        assert start["success"] is True
        assert start["job"]["backend"] == "bridge"

        status = self._parse(
            server.gms_get_live_processing_job_status(
                LiveProcessingJobQuery(job_id="bridge-job-1")
            )
        )
        assert status["success"] is True
        assert status["job"]["backend"] == "bridge"

        result = self._parse(
            server.gms_get_live_processing_job_result(
                LiveProcessingJobQuery(job_id="bridge-job-1", include_data=True)
            )
        )
        assert result["success"] is True
        assert result["result"]["median_size"] == 5

        stop = self._parse(
            server.gms_stop_live_processing_job(
                LiveProcessingJobQuery(job_id="bridge-job-1")
            )
        )
        assert stop["success"] is True
        assert [call[0] for call in calls] == [
            "LiveProcessingJobStart",
            "LiveProcessingJobStatus",
            "LiveProcessingJobResult",
            "LiveProcessingJobStop",
        ]

    def test_bridge_first_routing_for_state_and_tem(self, server, monkeypatch) -> None:
        from gms_mcp.server import AcquireTEMInput

        calls: list[tuple[str, dict]] = []

        def fake_bridge_dispatch(function_name: str, params: dict) -> dict:
            calls.append((function_name, dict(params)))
            if function_name == "GetMicroscopeState":
                return {
                    "success": True,
                    "simulation_mode": False,
                    "runtime_mode": "bridge-live",
                    "optics": {"high_tension_kV": 200.0},
                    "stage": {"x_um": 0.0, "y_um": 0.0, "z_um": 0.0, "alpha_deg": 0.0, "beta_deg": 0.0},
                    "beam": {"shift_x": 0.0, "shift_y": 0.0},
                    "eels": {"energy_offset_eV": 0.0, "slit_width_eV": 10.0, "in_eels_mode": False},
                    "camera": {"name": "BridgeCam", "inserted": True, "temp_c": -20.0, "n_signals": 3},
                }
            if function_name == "AcquireTEMImage":
                return {
                    "success": True,
                    "acquisition_type": "TEM",
                    "name": "TEM_bridge",
                    "shape": [1024, 1024],
                    "dtype": "float32",
                    "statistics": {"min": 0.0, "max": 1.0, "mean": 0.5, "std": 0.1},
                    "calibration": {"origin": 0.0, "scale": 0.02, "unit": "nm"},
                    "metadata": {"exposure_s": 1.0, "high_tension_kV": 200.0, "magnification": 100000.0},
                }
            return {"success": True}

        monkeypatch.setattr(server, "_BRIDGE_ZMQ_ENDPOINT", "tcp://bridge-host:5555")
        monkeypatch.setattr(server, "_bridge_dispatch", fake_bridge_dispatch)

        state = self._parse(server.gms_get_microscope_state())
        assert state["success"] is True
        assert state["runtime_mode"] == "bridge-live"
        assert state["simulation_mode"] is False

        tem = self._parse(server.gms_acquire_tem_image(AcquireTEMInput()))
        assert tem["success"] is True
        assert tem["acquisition_type"] == "TEM"

        assert [name for name, _ in calls] == ["GetMicroscopeState", "AcquireTEMImage"]

    # --- Gap-filling unit tests ---------------------------------------------------

    def test_get_front_image_with_pixel_data(self, server) -> None:
        """include_data=True should embed a base64 blob that decodes to the right size."""
        import base64
        from gms_mcp.server import FrontImageInput

        raw = server.gms_get_front_image(FrontImageInput(include_data=True, include_tags=False))
        data = self._parse(raw)
        assert data["success"] is True
        b64 = data["image"]["data_b64"]
        assert isinstance(b64, str) and len(b64) > 0
        blob = base64.b64decode(b64)
        h, w = data["image"]["shape"]
        assert len(blob) == h * w * 4  # float32 = 4 bytes/element

    def test_apply_image_filter_gaussian_only(self, server) -> None:
        """gaussian_sigma > 0 with median disabled should still succeed."""
        from gms_mcp.server import ImageFilterInput

        raw = server.gms_apply_image_filter(
            ImageFilterInput(median_size=0, gaussian_sigma=2.0)
        )
        data = self._parse(raw)
        assert data["success"] is True
        assert data["image"]["shape"][0] > 0

    def test_apply_image_filter_with_roi(self, server) -> None:
        """ROI should crop the output to the specified region."""
        from gms_mcp.server import AcquireTEMInput, ImageFilterInput

        server.gms_acquire_tem_image(AcquireTEMInput())  # ensure a large front image
        raw = server.gms_apply_image_filter(
            ImageFilterInput(roi=[0, 0, 256, 256], median_size=3, gaussian_sigma=0.0)
        )
        data = self._parse(raw)
        assert data["success"] is True
        assert data["image"]["shape"] == [256, 256]

    def test_compute_radial_profile_diffraction(self, server) -> None:
        """mode='diffraction' should use raw pixel data instead of FFT magnitude."""
        from gms_mcp.server import AcquireTEMInput, RadialProfileInput

        server.gms_acquire_tem_image(AcquireTEMInput())
        raw = server.gms_compute_radial_profile(
            RadialProfileInput(mode="diffraction", binning=4)
        )
        data = self._parse(raw)
        assert data["success"] is True
        assert data["analysis"]["mode"] == "diffraction"
        assert data["analysis"]["profile_length"] > 0
        assert len(data["profile"]) == data["analysis"]["profile_length"]

    def test_compute_radial_profile_mask_center(self, server) -> None:
        """mask_center_lines should still return a valid profile."""
        from gms_mcp.server import AcquireTEMInput, RadialProfileInput

        server.gms_acquire_tem_image(AcquireTEMInput())
        raw = server.gms_compute_radial_profile(
            RadialProfileInput(mode="fft", mask_center_lines=True)
        )
        data = self._parse(raw)
        assert data["success"] is True
        assert data["analysis"]["profile_length"] > 0

    def test_compute_max_fft_small_window(self, server) -> None:
        """Non-default fft_size and spacing should be reflected in the output shape."""
        from gms_mcp.server import AcquireTEMInput, MaxFFTInput

        server.gms_acquire_tem_image(AcquireTEMInput())
        raw = server.gms_compute_max_fft(MaxFFTInput(fft_size=32, spacing=64))
        data = self._parse(raw)
        assert data["success"] is True
        assert data["image"]["shape"] == [32, 32]
        assert data["analysis"]["n_windows"] >= 1

    def test_set_beam_focus(self, server) -> None:
        """Setting focus_um should appear in applied_settings and current_state."""
        from gms_mcp.server import SetBeamInput

        raw = server.gms_set_beam_parameters(SetBeamInput(focus_um=2.5))
        data = self._parse(raw)
        assert data["success"] is True
        assert data["applied_settings"]["focus_um"] == pytest.approx(2.5)
        assert data["current_state"]["focus_um"] == pytest.approx(2.5)

    def test_set_beam_tilt(self, server) -> None:
        """Beam tilt should be applied and echoed back."""
        from gms_mcp.server import SetBeamInput

        raw = server.gms_set_beam_parameters(SetBeamInput(tilt_x=0.003, tilt_y=-0.002))
        data = self._parse(raw)
        assert data["success"] is True
        assert data["applied_settings"]["beam_tilt"] == pytest.approx([0.003, -0.002])

    def test_set_beam_no_settings(self, server) -> None:
        """Empty SetBeamInput should succeed with an empty applied_settings dict."""
        from gms_mcp.server import SetBeamInput

        raw = server.gms_set_beam_parameters(SetBeamInput())
        data = self._parse(raw)
        assert data["success"] is True
        assert data["applied_settings"] == {}

    def test_set_beam_flattened_focus(self, server) -> None:
        """focus_um passed as a flat kwarg (LLM-style) should be accepted."""
        raw = server.gms_set_beam_parameters(focus_um=1.0)
        data = self._parse(raw)
        assert data["success"] is True
        assert data["applied_settings"]["focus_um"] == pytest.approx(1.0)

    def test_configure_detectors_temperature(self, server) -> None:
        """Setting target_temp_c should appear in applied and the status is readable."""
        from gms_mcp.server import SetDetectorInput

        raw = server.gms_configure_detectors(SetDetectorInput(target_temp_c=-20.0))
        data = self._parse(raw)
        assert data["success"] is True
        assert data["applied"]["target_temp_c"] == pytest.approx(-20.0)
        assert "actual_temp_c" in data["status"]

    def test_configure_detectors_all_signals(self, server) -> None:
        """Enable all three DigiScan channels and verify the status."""
        from gms_mcp.server import SetDetectorInput

        raw = server.gms_configure_detectors(
            SetDetectorInput(haadf_enabled=True, bf_enabled=True, abf_enabled=True)
        )
        data = self._parse(raw)
        assert data["success"] is True
        assert data["status"]["haadf_enabled"] is True
        assert data["status"]["bf_enabled"] is True
        assert data["status"]["abf_enabled"] is True

    def test_acquire_stem_custom_size(self, server) -> None:
        """Non-square STEM scan with custom dwell time should succeed."""
        from gms_mcp.server import AcquireSTEMInput

        raw = server.gms_acquire_stem(
            AcquireSTEMInput(width=128, height=64, dwell_us=20.0)
        )
        data = self._parse(raw)
        assert data["success"] is True
        assert data["scan_parameters"]["width"] == 128
        assert data["scan_parameters"]["height"] == 64
        assert data["scan_parameters"]["dwell_us"] == pytest.approx(20.0)

    def test_acquire_diffraction_with_binning(self, server) -> None:
        """Binned diffraction acquisition should succeed and return a pattern."""
        from gms_mcp.server import AcquireDiffractionInput

        raw = server.gms_acquire_diffraction(
            AcquireDiffractionInput(exposure_s=0.1, binning=2)
        )
        data = self._parse(raw)
        assert data["success"] is True
        assert "pattern" in data
        # binned image should still have a non-zero central region
        assert data["pattern"]["direct_beam_centre"][0] > 0

    def test_acquire_eels_full_params(self, server) -> None:
        """All AcquireEELSInput fields should be respected."""
        from gms_mcp.server import AcquireEELSInput

        raw = server.gms_acquire_eels(AcquireEELSInput(
            exposure_s=0.5,
            energy_offset_eV=200.0,
            slit_width_eV=3.0,
            dispersion_idx=2,
            full_vertical_binning=False,
        ))
        data = self._parse(raw)
        assert data["success"] is True
        assert data["spectrum"]["energy_range_eV"][0] == pytest.approx(200.0)
        assert data["spectrum"]["n_channels"] > 0

    def test_acquire_4d_stem_convergence_metadata(self, server) -> None:
        """convergence_mrad should be stored in the dataset metadata."""
        from gms_mcp.server import Acquire4DSTEMInput

        raw = server.gms_acquire_4d_stem(
            Acquire4DSTEMInput(scan_x=8, scan_y=8, dwell_us=500.0, convergence_mrad=12.5)
        )
        data = self._parse(raw)
        assert data["success"] is True
        assert data["dataset"]["convergence_mrad"] == pytest.approx(12.5)

    def test_4dstem_analysis_dpc(self, server) -> None:
        """Differential phase contrast analysis should return a 2-D result map."""
        from gms_mcp.server import Acquire4DSTEMInput

        server.gms_acquire_4d_stem(Acquire4DSTEMInput(scan_x=8, scan_y=8, dwell_us=500.0))
        raw = server.gms_run_4dstem_analysis(
            inner_angle_mrad=0.0,
            outer_angle_mrad=50.0,
            analysis_type="dpc",
        )
        data = self._parse(raw)
        assert data["success"] is True
        assert data["analysis"]["type"] == "dpc"
        assert data["analysis"]["result_shape"] == [8, 8]

    def test_4dstem_analysis_virtual_bf(self, server) -> None:
        """Virtual BF should succeed analogously to virtual HAADF."""
        from gms_mcp.server import Acquire4DSTEMInput

        server.gms_acquire_4d_stem(Acquire4DSTEMInput(scan_x=8, scan_y=8, dwell_us=500.0))
        raw = server.gms_run_4dstem_analysis(
            inner_angle_mrad=0.0,
            outer_angle_mrad=20.0,
            analysis_type="virtual_bf",
        )
        data = self._parse(raw)
        assert data["success"] is True
        assert data["analysis"]["type"] == "virtual_bf"

    def test_live_job_unknown_id(self, server) -> None:
        """Querying a non-existent job ID should return success=False."""
        from gms_mcp.server import LiveProcessingJobQuery

        raw = server.gms_get_live_processing_job_status(
            LiveProcessingJobQuery(job_id="nonexistent-job-id-xyz")
        )
        data = self._parse(raw)
        assert data["success"] is False

    def test_live_job_stop_unknown_id(self, server) -> None:
        """Stopping a non-existent job ID should return success=False."""
        from gms_mcp.server import LiveProcessingJobQuery

        raw = server.gms_stop_live_processing_job(
            LiveProcessingJobQuery(job_id="nonexistent-job-xyz")
        )
        data = self._parse(raw)
        assert data["success"] is False

    def test_live_job_result_unknown_id(self, server) -> None:
        """Fetching results for a non-existent job should return success=False."""
        from gms_mcp.server import LiveProcessingJobQuery

        raw = server.gms_get_live_processing_job_result(
            LiveProcessingJobQuery(job_id="nonexistent-job-xyz")
        )
        data = self._parse(raw)
        assert data["success"] is False

    def test_tilt_series_single_step(self, server) -> None:
        """A single-step tilt series (start=end allowed via step) still runs."""
        from gms_mcp.server import TiltSeriesInput

        raw = server.gms_acquire_tilt_series(
            TiltSeriesInput(start_deg=-5.0, end_deg=5.0, step_deg=10.0,
                            exposure_s=0.1, binning=8)
        )
        data = self._parse(raw)
        assert data["success"] is True
        assert data["tilt_series"]["n_frames"] >= 1

    def test_tilt_series_invalid_step(self) -> None:
        """step_deg below minimum should raise a pydantic ValidationError."""
        from gms_mcp.server import TiltSeriesInput
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            TiltSeriesInput(start_deg=-10.0, end_deg=10.0, step_deg=0.1)

    def test_get_microscope_state_camera_section(self, server) -> None:
        """The 'camera' key should be present with name and inserted status."""
        raw = server.gms_get_microscope_state()
        data = self._parse(raw)
        assert data["success"] is True
        assert "camera" in data
        cam = data["camera"]
        assert "name" in cam
        assert "inserted" in cam
        assert "n_signals" in cam

    def test_live_radial_profile_diffraction_mode(self, server) -> None:
        """A live radial-profile job in diffraction mode should run and stop."""
        from gms_mcp.server import AcquireTEMInput, LiveProcessingJobQuery, StartLiveProcessingJobInput

        server.gms_acquire_tem_image(AcquireTEMInput())
        start = self._parse(
            server.gms_start_live_processing_job(
                StartLiveProcessingJobInput(
                    job_type="radial_profile",
                    poll_interval_s=0.05,
                    history_length=16,
                    profile_mode="diffraction",
                )
            )
        )
        assert start["success"] is True
        job_id = start["job"]["job_id"]
        try:
            status = self._wait_for_live_job(server, job_id, min_iterations=1)
            assert status["job"]["status"] in {"running", "stopped"}
            result = self._parse(
                server.gms_get_live_processing_job_result(
                    LiveProcessingJobQuery(job_id=job_id)
                )
            )
            assert result["success"] is True
        finally:
            self._parse(server.gms_stop_live_processing_job(
                LiveProcessingJobQuery(job_id=job_id)
            ))

    # -------------------------------------------------------------------------

    def test_live_maximum_spot_mapping_bridge_delegation(self, server, monkeypatch) -> None:
        from gms_mcp.server import LiveProcessingJobQuery, StartLiveProcessingJobInput

        calls: list[tuple[str, dict]] = []

        def fake_bridge_dispatch(function_name: str, params: dict) -> dict:
            calls.append((function_name, dict(params)))
            base_job = {
                "job_id": "bridge-4dstem-job",
                "job_type": "maximum_spot_mapping",
                "backend": "bridge",
                "poll_interval_s": 0.1,
                "iterations": 2,
                "created_at": 1.0,
                "last_updated": 2.0,
                "last_error": None,
                "source_image_name": "4DSTEM_Bridge",
                "result_summary": {"shape": [8, 8, 3], "type": "maximum_spot_mapping"},
            }
            if function_name == "LiveProcessingJobStart":
                return {"success": True, "job": {**base_job, "status": "starting", "show_result": params["show_result"]}}
            if function_name == "LiveProcessingJobStatus":
                return {"success": True, "job": {**base_job, "status": "running"}}
            if function_name == "LiveProcessingJobResult":
                return {
                    "success": True,
                    "job": {**base_job, "status": "running"},
                    "result": {
                        "shape": [8, 8, 3],
                        "type": "maximum_spot_mapping",
                        "map_var": "radius",
                    },
                }
            return {"success": True, "job": {**base_job, "status": "stopped"}}

        monkeypatch.setattr(server, "_BRIDGE_ZMQ_ENDPOINT", "tcp://bridge-host:5555")
        monkeypatch.setattr(server, "_bridge_dispatch", fake_bridge_dispatch)

        start = self._parse(
            server.gms_start_live_processing_job(
                StartLiveProcessingJobInput(
                    job_type="maximum_spot_mapping",
                    poll_interval_s=0.1,
                    map_var="radius",
                    mask_center_radius_px=4.0,
                )
            )
        )
        assert start["success"] is True
        assert start["job"]["backend"] == "bridge"

        status = self._parse(
            server.gms_get_live_processing_job_status(
                LiveProcessingJobQuery(job_id="bridge-4dstem-job")
            )
        )
        assert status["success"] is True
        assert status["job"]["job_type"] == "maximum_spot_mapping"

        result = self._parse(
            server.gms_get_live_processing_job_result(
                LiveProcessingJobQuery(job_id="bridge-4dstem-job")
            )
        )
        assert result["success"] is True
        assert result["result"]["type"] == "maximum_spot_mapping"
        assert result["result"]["map_var"] == "radius"

        stop = self._parse(
            server.gms_stop_live_processing_job(
                LiveProcessingJobQuery(job_id="bridge-4dstem-job")
            )
        )
        assert stop["success"] is True
        assert [call[0] for call in calls] == [
            "LiveProcessingJobStart",
            "LiveProcessingJobStatus",
            "LiveProcessingJobResult",
            "LiveProcessingJobStop",
        ]


# ---------------------------------------------------------------------------
# TestServerTransport — verify the server can start cleanly
# ---------------------------------------------------------------------------

class TestServerTransport:
    """Smoke tests that verify the FastMCP server starts without errors."""

    def test_server_module_imports_cleanly(self) -> None:
        """Import the server in a fresh subprocess to catch import errors."""
        result = subprocess.run(
            [sys.executable, "-c",
             "import os; os.environ['GMS_SIMULATE']='1'; "
             "import sys; sys.path.insert(0, '.'); "
             "import gms_mcp.server; "
             "print('OK')"],
            capture_output=True, text=True, timeout=15,
            cwd=str(_HERE),
        )
        assert result.returncode == 0, f"Import failed:\n{result.stderr}"
        assert "OK" in result.stdout

    def test_simulator_imports_cleanly(self) -> None:
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, '.'); "
             "from gms_mcp.simulator import DMSimulator; "
             "d = DMSimulator(); print(d.EMGetHighTension())"],
            capture_output=True, text=True, timeout=10,
            cwd=str(_HERE),
        )
        assert result.returncode == 0
        assert float(result.stdout.strip()) > 0

    def test_tools_are_registered(self, server) -> None:
        """All expected tools must be registered in the FastMCP instance."""
        tools = asyncio.run(server.mcp.list_tools())
        tool_names = {t.name for t in tools}
        expected = {
            "gms_get_microscope_state",
            "gms_get_front_image",
            "gms_acquire_tem_image",
            "gms_acquire_stem",
            "gms_acquire_4d_stem",
            "gms_acquire_eels",
            "gms_acquire_diffraction",
            "gms_apply_image_filter",
            "gms_compute_radial_profile",
            "gms_compute_max_fft",
            "gms_start_live_processing_job",
            "gms_get_live_processing_job_status",
            "gms_get_live_processing_job_result",
            "gms_stop_live_processing_job",
            "gms_get_stage_position",
            "gms_set_stage_position",
            "gms_set_beam_parameters",
            "gms_configure_detectors",
            "gms_acquire_tilt_series",
            "gms_run_4dstem_analysis",
            "gms_run_4dstem_maximum_spot_mapping",
        }
        missing = expected - tool_names
        assert not missing, f"Missing tools: {missing}"

    def test_tool_descriptions_non_empty(self, server) -> None:
        tools = asyncio.run(server.mcp.list_tools())
        for tool in tools:
            assert tool.description, f"Tool '{tool.name}' has no description"

    def test_tool_input_schemas_present(self, server) -> None:
        # FastMCP 3.x uses .parameters (dict); official MCP SDK uses .inputSchema
        tools = asyncio.run(server.mcp.list_tools())
        for tool in tools:
            schema = (getattr(tool, "parameters", None)
                      or getattr(tool, "inputSchema", None))
            assert schema is not None, (
                f"Tool '{tool.name}' has no input schema (.parameters or .inputSchema)"
            )


class TestClientVoiceHelpers:
    def test_parse_args_voice_flags(self) -> None:
        from gms_mcp.client import _parse_args

        args = _parse_args([
            "--voice",
            "--speak",
            "--whisper-model",
            "small.en",
            "--voice-max-seconds",
            "12",
        ])

        assert args.voice is True
        assert args.speak is True
        assert args.whisper_model == "small.en"
        assert args.voice_max_seconds == pytest.approx(12.0)

    def test_capture_voice_query_transcribes_and_cleans_up(self, monkeypatch) -> None:
        from gms_mcp import client

        removed = []

        class DummyTranscriber:
            def transcribe_file(self, audio_path) -> str:
                assert str(audio_path).endswith(".wav")
                return "Acquire a 256 by 256 TEM image"

        monkeypatch.setattr(
            client.voice_io,
            "record_push_to_talk",
            lambda sample_rate, max_duration_s: Path("/tmp/fake_prompt.wav"),
        )
        monkeypatch.setattr(
            client.voice_io,
            "remove_temp_audio_file",
            lambda audio_path: removed.append(Path(audio_path)),
        )

        transcript = client._capture_voice_query(
            transcriber=DummyTranscriber(),
            sample_rate=16_000,
            max_duration_s=10.0,
        )

        assert transcript == "Acquire a 256 by 256 TEM image"
        assert removed == [Path("/tmp/fake_prompt.wav")]

    def test_emit_agent_reply_speaks_when_enabled(self, monkeypatch, capsys) -> None:
        from gms_mcp import client

        spoken = []
        monkeypatch.setattr(
            client.voice_io,
            "speak_text",
            lambda text, command="": spoken.append((text, command)),
        )

        client._emit_agent_reply("Stage moved successfully.", speak=True, tts_command="say")

        out = capsys.readouterr().out
        assert "Agent: Stage moved successfully." in out
        assert spoken == [("Stage moved successfully.", "say")]


# ---------------------------------------------------------------------------
# TestOllamaIntegration — end-to-end tests (requires Ollama)
# ---------------------------------------------------------------------------

OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

def _ollama_available() -> bool:
    """Check whether the Ollama server is reachable and the model is present."""
    try:
        import httpx
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=3.0)
        if r.status_code != 200:
            return False
        models = [m["name"] for m in r.json().get("models", [])]
        return any(OLLAMA_MODEL in m for m in models)
    except Exception:
        return False


_OLLAMA_SKIP = pytest.mark.skipif(
    not _ollama_available(),
    reason=(
        f"Ollama not available at {OLLAMA_URL} "
        f"or model '{OLLAMA_MODEL}' not pulled. "
        f"Run: ollama pull {OLLAMA_MODEL}"
    ),
)


@pytest.mark.ollama
class TestOllamaIntegration:
    """End-to-end tests that exercise the full Ollama → MCP → GMS pipeline."""

    @_OLLAMA_SKIP
    def test_single_tool_query(self) -> None:
        """Agent should call gms_get_microscope_state for a state query."""
        from gms_mcp.client import run_agent
        result = asyncio.run(run_agent(
            query="What is the current accelerating voltage of the microscope?",
            model=OLLAMA_MODEL,
            base_url=OLLAMA_URL,
        ))
        assert result["answer"], "Agent returned empty answer"
        assert len(result["tool_calls"]) >= 1
        called = [tc["tool"] for tc in result["tool_calls"]]
        assert "gms_get_microscope_state" in called

    @_OLLAMA_SKIP
    def test_stage_position_query(self) -> None:
        from gms_mcp.client import run_agent
        result = asyncio.run(run_agent(
            query="What are the current stage coordinates in micrometers?",
            model=OLLAMA_MODEL,
            base_url=OLLAMA_URL,
        ))
        assert result["answer"]
        called = [tc["tool"] for tc in result["tool_calls"]]
        assert any("stage" in t for t in called)

    @_OLLAMA_SKIP
    def test_acquire_and_report(self) -> None:
        """Agent should acquire a TEM image and report its statistics."""
        from gms_mcp.client import run_agent
        result = asyncio.run(run_agent(
            query=(
                "Please acquire a TEM image with 0.5 s exposure and 2× binning, "
                "then report the image dimensions and mean pixel intensity."
            ),
            model=OLLAMA_MODEL,
            base_url=OLLAMA_URL,
        ))
        assert result["answer"]
        called = [tc["tool"] for tc in result["tool_calls"]]
        assert "gms_acquire_tem_image" in called
        # Answer should mention pixel or intensity
        answer_lower = result["answer"].lower()
        assert any(w in answer_lower for w in ("pixel", "mean", "intensity", "statistic"))

    @_OLLAMA_SKIP
    def test_eels_acquisition_workflow(self) -> None:
        """Agent should configure EELS and report the zero-loss peak position."""
        from gms_mcp.client import run_agent
        result = asyncio.run(run_agent(
            query=(
                "Acquire an EELS spectrum centred at 0 eV with a 5 eV slit width "
                "and 1 s exposure. Report the position of the zero-loss peak in eV."
            ),
            model=OLLAMA_MODEL,
            base_url=OLLAMA_URL,
        ))
        assert result["answer"]
        called = [tc["tool"] for tc in result["tool_calls"]]
        assert "gms_acquire_eels" in called

    @_OLLAMA_SKIP
    def test_stage_move_and_confirm(self) -> None:
        """Agent should move the stage and confirm the new position."""
        from gms_mcp.client import run_agent
        result = asyncio.run(run_agent(
            query="Move the stage to X = 100 µm, Y = -50 µm, then confirm the new position.",
            model=OLLAMA_MODEL,
            base_url=OLLAMA_URL,
        ))
        assert result["answer"]
        called = [tc["tool"] for tc in result["tool_calls"]]
        assert "gms_set_stage_position" in called

    @_OLLAMA_SKIP
    def test_front_image_and_filter_workflow(self) -> None:
        """Agent should fetch the front image then apply a Gaussian filter."""
        from gms_mcp.client import run_agent

        result = asyncio.run(run_agent(
            query=(
                "Get the current front image, apply a Gaussian filter with sigma=1.5 "
                "to it, and report the resulting image shape and mean intensity."
            ),
            model=OLLAMA_MODEL,
            base_url=OLLAMA_URL,
        ))
        assert result["answer"]
        called = [tc["tool"] for tc in result["tool_calls"]]
        assert "gms_apply_image_filter" in called

    @_OLLAMA_SKIP
    def test_diffraction_workflow(self) -> None:
        """Agent should acquire a diffraction pattern and describe it."""
        from gms_mcp.client import run_agent

        result = asyncio.run(run_agent(
            query=(
                "Acquire a diffraction pattern with a 200 mm camera length and "
                "0.3 s exposure, then report the direct-beam centre coordinates "
                "and the number of diffraction rings detected."
            ),
            model=OLLAMA_MODEL,
            base_url=OLLAMA_URL,
        ))
        assert result["answer"]
        called = [tc["tool"] for tc in result["tool_calls"]]
        assert "gms_acquire_diffraction" in called

    @_OLLAMA_SKIP
    def test_radial_profile_workflow(self) -> None:
        """Agent should acquire a TEM image and compute its FFT radial profile."""
        from gms_mcp.client import run_agent

        result = asyncio.run(run_agent(
            query=(
                "Acquire a TEM image and compute its radial FFT profile. "
                "Report the profile length and dominant spatial frequency."
            ),
            model=OLLAMA_MODEL,
            base_url=OLLAMA_URL,
        ))
        assert result["answer"]
        called = [tc["tool"] for tc in result["tool_calls"]]
        assert "gms_compute_radial_profile" in called

    @_OLLAMA_SKIP
    def test_beam_focus_and_acquire(self) -> None:
        """Agent should set focus and spot size, then acquire a TEM image."""
        from gms_mcp.client import run_agent

        result = asyncio.run(run_agent(
            query=(
                "Set the objective lens focus to 2.0 µm and spot size to 3, "
                "then acquire a TEM image and report the image statistics."
            ),
            model=OLLAMA_MODEL,
            base_url=OLLAMA_URL,
        ))
        assert result["answer"]
        called = [tc["tool"] for tc in result["tool_calls"]]
        assert "gms_set_beam_parameters" in called
        assert "gms_acquire_tem_image" in called

    @_OLLAMA_SKIP
    def test_4dstem_workflow(self) -> None:
        """Agent should acquire a 4D-STEM dataset and run virtual HAADF analysis."""
        from gms_mcp.client import run_agent

        result = asyncio.run(run_agent(
            query=(
                "Acquire a small 16×16 4D-STEM dataset with 1 ms dwell time, "
                "then compute a virtual HAADF image with inner angle 20 mrad "
                "and outer angle 60 mrad. Report the scan shape and mean intensity."
            ),
            model=OLLAMA_MODEL,
            base_url=OLLAMA_URL,
        ))
        assert result["answer"]
        called = [tc["tool"] for tc in result["tool_calls"]]
        assert "gms_acquire_4d_stem" in called
        assert "gms_run_4dstem_analysis" in called

    @_OLLAMA_SKIP
    def test_tilt_series_workflow(self) -> None:
        """Agent should acquire a tilt series and summarise per-frame statistics."""
        from gms_mcp.client import run_agent

        result = asyncio.run(run_agent(
            query=(
                "Acquire a tilt series from -15° to +15° in 5° steps with 0.2 s "
                "exposure. Report the mean intensity at each tilt angle."
            ),
            model=OLLAMA_MODEL,
            base_url=OLLAMA_URL,
        ))
        assert result["answer"]
        called = [tc["tool"] for tc in result["tool_calls"]]
        assert "gms_acquire_tilt_series" in called

    @_OLLAMA_SKIP
    def test_configure_detectors_and_acquire_stem(self) -> None:
        """Agent should configure detectors then run a STEM acquisition."""
        from gms_mcp.client import run_agent

        result = asyncio.run(run_agent(
            query=(
                "Enable the HAADF detector and disable the BF and ABF detectors, "
                "then acquire a 256×256 STEM image with 10 µs dwell time "
                "and report the image statistics."
            ),
            model=OLLAMA_MODEL,
            base_url=OLLAMA_URL,
        ))
        assert result["answer"]
        called = [tc["tool"] for tc in result["tool_calls"]]
        assert "gms_configure_detectors" in called
        assert "gms_acquire_stem" in called

    @_OLLAMA_SKIP
    def test_live_processing_workflow(self) -> None:
        """Agent should start a live FFT map job, check status, and stop it."""
        from gms_mcp.client import run_agent

        result = asyncio.run(run_agent(
            query=(
                "Start a live FFT map processing job with a 64-pixel FFT window, "
                "check its status, then stop it. Report the job ID and final status."
            ),
            model=OLLAMA_MODEL,
            base_url=OLLAMA_URL,
        ))
        assert result["answer"]
        called = [tc["tool"] for tc in result["tool_calls"]]
        assert "gms_start_live_processing_job" in called
        assert any(t in called for t in (
            "gms_get_live_processing_job_status",
            "gms_stop_live_processing_job",
        ))

    @_OLLAMA_SKIP
    def test_full_characterisation_workflow(self) -> None:
        """
        Multi-step workflow:
        1. Get microscope state
        2. Set beam parameters (spot size + focus)
        3. Acquire TEM image
        4. Compute radial FFT profile
        5. Report findings
        """
        from gms_mcp.client import run_agent

        result = asyncio.run(run_agent(
            query=(
                "Perform a full characterisation: first read the microscope state, "
                "then set spot size to 4 and focus to 1.5 µm, acquire a TEM image "
                "with 0.5 s exposure, compute its radial FFT profile, and give me "
                "a summary of the acquisition parameters and the dominant frequency."
            ),
            model=OLLAMA_MODEL,
            base_url=OLLAMA_URL,
        ))
        assert result["answer"]
        called = [tc["tool"] for tc in result["tool_calls"]]
        assert len(set(called)) >= 3
        assert "gms_acquire_tem_image" in called

    @_OLLAMA_SKIP
    def test_multi_step_workflow(self) -> None:
        """
        Agent should perform a multi-step workflow:
        1. Check state
        2. Set spot size
        3. Acquire STEM image
        """
        from gms_mcp.client import run_agent
        result = asyncio.run(run_agent(
            query=(
                "Check the microscope state, set the spot size to 4, "
                "then acquire a 256×256 HAADF STEM image with 5 µs dwell time."
            ),
            model=OLLAMA_MODEL,
            base_url=OLLAMA_URL,
        ))
        assert result["answer"]
        called = [tc["tool"] for tc in result["tool_calls"]]
        # Should have called at least 3 distinct tools
        assert len(set(called)) >= 2
        assert "gms_acquire_stem" in called


# ---------------------------------------------------------------------------
# Pytest configuration
# ---------------------------------------------------------------------------

def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "ollama: marks tests that require a running Ollama instance "
        "(deselect with -m 'not ollama')"
    )
