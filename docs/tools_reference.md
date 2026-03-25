# Tools Reference

All 12 GMS-MCP tools, their Pydantic-validated parameters, and JSON response schemas.

---

## `gms_get_microscope_state`

Read the current state of all microscope subsystems. **Always call this first.**

**Parameters:** none

**Returns:**
```json
{
  "success": true,
  "simulation_mode": false,
  "optics": {
    "high_tension_kV": 200.0,
    "spot_size": 3,
    "brightness": 0.5,
    "focus_um": 0.0,
    "magnification": 50000.0,
    "operation_mode": "TEM",
    "camera_length_mm": 100.0
  },
  "stage": { "x_um": 0.0, "y_um": 0.0, "z_um": 0.0, "alpha_deg": 0.0, "beta_deg": 0.0 },
  "eels": { "energy_offset_eV": 0.0, "slit_width_eV": 10.0, "in_eels_mode": false },
  "camera": { "name": "OneView", "inserted": true, "temp_c": -24.8, "n_signals": 4 }
}
```

---

## `gms_acquire_tem_image`

Acquire a TEM or HRTEM image.

| Parameter | Type | Range | Default | Description |
|---|---|---|---|---|
| `exposure_s` | float | [0.001, 60] | 1.0 | Camera exposure in seconds |
| `binning` | int | {1,2,4,8} | 1 | Camera binning factor |
| `processing` | int | {1,2,3} | 3 | 1=raw, 2=dark, 3=dark+gain |
| `roi` | list[int] or null | len=4 | null | [top, left, bottom, right] in pixels |

**Returns:** image shape, dtype, statistics (min/max/mean/std), pixel calibration, metadata.

---

## `gms_acquire_stem`

Acquire a STEM image (HAADF / BF / ABF) via DigiScan.

| Parameter | Type | Range | Default | Description |
|---|---|---|---|---|
| `width` | int | [64, 4096] | 512 | Scan width in pixels |
| `height` | int | [64, 4096] | 512 | Scan height in pixels |
| `dwell_us` | float | [0.5, 10000] | 10.0 | Pixel dwell time (µs) |
| `rotation_deg` | float | [-180, 180] | 0.0 | Scan rotation (degrees) |
| `signals` | list[int] | [0,1,2,3] | [0,1] | DigiScan channels (0=HAADF, 1=BF, 2=ABF) |

**Returns:** image summary + `scan_parameters.total_frame_time_s`.

---

## `gms_acquire_4d_stem`

Acquire a 4D-STEM / NBED dataset.

| Parameter | Type | Range | Default | Description |
|---|---|---|---|---|
| `scan_x` | int | [8, 512] | 64 | Scan positions in X |
| `scan_y` | int | [8, 512] | 64 | Scan positions in Y |
| `dwell_us` | float | [100, 100000] | 1000.0 | Per-pattern dwell time (µs) |
| `camera_length_mm` | float or null | [20, 2000] | null | Camera length; null = keep current |
| `convergence_mrad` | float or null | [0.1, 50] | null | Convergence semi-angle (metadata only) |

**Returns:** dataset shape, total patterns, estimated file size (MB), acquisition time.

---

## `gms_acquire_eels`

Acquire an EELS spectrum using the Gatan Imaging Filter.

| Parameter | Type | Range | Default | Description |
|---|---|---|---|---|
| `exposure_s` | float | [0.001, 60] | 1.0 | Spectrometer exposure (s) |
| `energy_offset_eV` | float | [-200, 3000] | 0.0 | Drift tube energy offset (eV) |
| `slit_width_eV` | float | [0, 100] | 10.0 | Energy slit width (eV); 0 = slit out |
| `dispersion_idx` | int | {0,1,2,3} | 0 | Dispersion: 0=0.1, 1=0.25, 2=0.5, 3=1.0 eV/ch |
| `full_vertical_binning` | bool | — | true | Apply full vertical CCD binning |

**Returns:** channel count, energy axis calibration, ZLP centre estimate, slit state.

---

## `gms_acquire_diffraction`

Acquire an electron diffraction pattern and extract d-spacings.

| Parameter | Type | Range | Default |
|---|---|---|---|
| `exposure_s` | float | [0.001, 60] | 0.5 |
| `camera_length_mm` | float or null | [20, 2000] | null |
| `binning` | int | {1,2,4,8} | 1 |

**Returns:** pattern shape, camera length, pixel scale (1/Å per pixel), ring radii (px), d-spacings (Å).

---

## `gms_get_stage_position`

Read all stage axes. No parameters.

**Returns:** `x_um`, `y_um`, `z_um` (µm), `alpha_deg`, `beta_deg`.

---

## `gms_set_stage_position`

Move stage. All parameters optional — only provided axes move.

| Parameter | Type | Range |
|---|---|---|
| `x_um` | float or null | [-5000, 5000] µm |
| `y_um` | float or null | [-5000, 5000] µm |
| `z_um` | float or null | [-500, 500] µm |
| `alpha_deg` | float or null | [-80, 80]° |
| `beta_deg` | float or null | [-30, 30]° |

**Returns:** new position after movement.

---

## `gms_set_beam_parameters`

Configure beam/optics. All parameters optional.

| Parameter | Type | Description |
|---|---|---|
| `spot_size` | int [1,11] | Condenser spot size index |
| `focus_um` | float | Absolute objective lens focus offset |
| `shift_x`, `shift_y` | float | Calibrated beam shift |
| `tilt_x`, `tilt_y` | float | Beam tilt (rad) |
| `obj_stig_x`, `obj_stig_y` | float | Objective stigmator |

---

## `gms_configure_detectors`

Configure camera and STEM detectors.

| Parameter | Type | Description |
|---|---|---|
| `insert_camera` | bool or null | True = insert, False = retract |
| `target_temp_c` | float [-60,30] | Target CCD temperature |
| `haadf_enabled` | bool or null | Enable DigiScan channel 0 |
| `bf_enabled` | bool or null | Enable DigiScan channel 1 |
| `abf_enabled` | bool or null | Enable DigiScan channel 2 |

---

## `gms_acquire_tilt_series`

Automated tomographic tilt series.

| Parameter | Type | Range | Default |
|---|---|---|---|
| `start_deg` | float | [-80, 0] | -60.0 |
| `end_deg` | float | [0, 80] | 60.0 |
| `step_deg` | float | [0.5, 10] | 2.0 |
| `exposure_s` | float | [0.001, 60] | 1.0 |
| `binning` | int | {1,2,4,8} | 2 |
| `save_dir` | str or null | — | null |

**Returns:** frame count, per-tilt statistics, elapsed time.

---

## `gms_run_4dstem_analysis`

Virtual detector / DPC / CoM analysis on a loaded 4D-STEM dataset.

| Parameter | Type | Range | Default |
|---|---|---|---|
| `inner_angle_mrad` | float | [0, 50] | 10.0 |
| `outer_angle_mrad` | float | [1, 50] | 40.0 |
| `analysis_type` | str | — | "virtual_haadf" |

Valid `analysis_type` values: `virtual_bf`, `virtual_haadf`, `com`, `dpc`, `strain`.

**Returns:** result shape, min/max/mean/std of the computed map.
