# DigitalMicrograph Python API Quick Reference

Reference for the GMS 3.60 Python API surface used by GMS-MCP.
All functions are called as `DM.<function_name>()` after
`import DigitalMicrograph as DM`.

> **Note**: This reference covers functions used by GMS-MCP.
> For the complete function listing for your GMS version, run
> `help(DM)` inside the GMS Python console, or run Gatan's
> `Output_DM_Python_help.py` script.

---

## Image Management

```python
# Create image from numpy array
img = DM.CreateImage(arr)               # arr: np.ndarray → Py_Image

# Retrieve images
front = DM.GetFrontImage()              # frontmost displayed image
found = DM.FindImageByName("HAADF")    # by title
found = DM.FindImageByID(42)            # by numeric ID

# Open / save files
img = DM.OpenImage("C:\\data\\sample.dm4")
DM.SaveImage(img, "C:\\data\\output.dm4")

# Numpy interop — IMPORTANT: returns a LIVE memory-mapped view
arr = img.GetNumArray()                 # modifications change the image
arr[:] = new_data                       # in-place write (correct)
arr = new_data                          # rebinds variable (WRONG)
img.UpdateImage()                       # refresh display after in-place edit
img.ShowImage()
img.SetName("My Image")
```

---

## Tag / Metadata System

```python
tags = img.GetTagGroup()                # root tag group

# Write
tags.SetTagAsString("Experiment:Operator", "R. dos Reis")
tags.SetTagAsFloat("Experiment:Dose_e_per_A2", 25.4)
tags.SetTagAsLong("Experiment:FrameCount", 100)

# Read — returns (success_bool, value)
ok, operator = tags.GetTagAsString("Experiment:Operator")
ok, dose     = tags.GetTagAsFloat("Experiment:Dose_e_per_A2")
ok, count    = tags.GetTagAsLong("Experiment:FrameCount")

# Calibration
origin, scale, unit = img.GetDimensionCalibration(0, 0)   # X axis
img.SetDimensionCalibration(0, 0.0, 0.0196, "nm", 0)      # 0.0196 nm/px
```

---

## Camera Manager (CM_*)

```python
camera = DM.CM_GetCurrentCamera()

# Acquisition parameters
acq = DM.CM_CreateAcquisitionParameters_FullCCD(
    camera,
    processing,   # 1=raw, 2=dark, 3=dark+gain
    exposure_s,
    binning_x, binning_y
)
DM.CM_SetExposure(acq, 2.0)
DM.CM_SetBinning(acq, 1, 1)
DM.CM_SetCCDReadArea(acq, top, left, bottom, right)
DM.CM_Validate_AcquisitionParameters(camera, acq)
img = DM.CM_AcquireImage(camera, acq)

# Camera info
name     = DM.CM_GetCameraName(camera)
inserted = DM.CM_GetCameraInserted(camera)
temp_c   = DM.CM_GetActualTemperature_C(camera)

# Insert / retract
DM.CM_SetCameraInserted(camera, 1)     # insert
DM.CM_SetCameraInserted(camera, 0)     # retract
DM.CM_SetTargetTemperature_C(camera, 1, -25.0)

# Dark reference
dark = DM.CM_CreateImageForAcquire(camera, acq, "Dark Ref")
DM.CM_AcquireDarkReference(camera, acq, dark, None)
```

---

## DigiScan / STEM (DS_*)

```python
DM.DSSetFrameSize(512, 512)            # width, height in pixels
DM.DSSetPixelTime(10.0)                # dwell time in µs
DM.DSSetRotation(0.0)                  # scan rotation in degrees
DM.DSSetFlybackTime(500.0)             # flyback in µs
DM.DSSetLineSync(0)                    # 0=off, 1=on

n = DM.DSGetNumberOfSignals()          # number of analog channels
DM.DSSetSignalEnabled(0, 1)            # channel 0 (HAADF) ON
DM.DSSetSignalEnabled(1, 1)            # channel 1 (BF) ON
DM.DSSetSignalEnabled(2, 0)            # channel 2 (ABF) OFF

DM.DSStartAcquisition()
DM.DSWaitUntilFinished()
DM.DSStopAcquisition()                 # for continuous mode
DM.DSSetContinuousMode(1)              # enable continuous scan
DM.DSSetBeamBlanked(1)                 # blank beam
```

---

## Imaging Filter / GIF (IF_*, IFC_*)

```python
DM.IFSetEELSMode()                     # switch to EELS
DM.IFSetImageMode()                    # switch to imaging
DM.IFSetEnergyLoss(300.0)              # energy offset in eV
eV = DM.IFGetEnergyLoss(0)            # read current offset
DM.IFSetSlitWidth(10.0)                # slit width in eV
DM.IFSetSlitIn(1)                      # insert slit

# IFC_ functions (GIF-specific)
DM.IFCSetEnergy(300.0)
DM.IFCSetSlitWidth(10.0)
DM.IFCSetSlitIn(1)
DM.IFCSetDriftTubeVoltage(300.0)
DM.IFCSetDriftTubeOn(1)
n = DM.IFCGetNumberofDispersions()
DM.IFCSetActiveDispersions(0)          # 0=finest dispersion
DM.IFCSetAperture(2)                   # entrance aperture index
```

---

## Microscope Control (EM_*)

```python
# High tension
ht = DM.EMGetHighTension()             # volts (e.g. 200000 for 200 kV)
ok = DM.EMCanGetHighTension()
DM.EMSetHighTensionOffset(5.0)
DM.EMSetHighTensionOffsetEnabled(True)

# Spot size, brightness, focus
DM.EMSetSpotSize(3)                    # index 1–11
DM.EMSetBrightness(0.5)
DM.EMSetFocus(f)
DM.EMChangeFocus(delta)

# Magnification
DM.EMSetMagIndex(idx)
mag = DM.EMGetMagnification()

# Beam shift / tilt
DM.EMSetCalibratedBeamShift(x, y)
DM.EMChangeCalibratedBeamShift(dx, dy)
DM.EMSetBeamTilt(x, y)
DM.EMSetImageShift(x, y)

# Stigmation
DM.EMSetObjectiveStigmation(x, y)
DM.EMChangeCondensorStigmation(dx, dy)

# Mode
mode = DM.EMGetOperationMode()         # "TEM", "STEM", "DIFFRACTION"
il   = DM.EMGetIlluminationMode()

# Camera length
DM.EMSetCameraLength(100.0)            # mm
cl = DM.EMGetCameraLength()
ok = DM.EMCanGetCameraLength()
```

---

## Stage (EM* stage functions)

```python
# Individual axes
x = DM.EMGetStageX()                   # µm
y = DM.EMGetStageY()
z = DM.EMGetStageZ()
a = DM.EMGetStageAlpha()               # degrees
b = DM.EMGetStageBeta()

DM.EMSetStageX(100.0)
DM.EMSetStageXY(100.0, 200.0)
DM.EMSetStageAlpha(-30.0)

# Multi-axis move: flags bitmask 1=X, 2=Y, 4=Z, 8=alpha, 16=beta
DM.EMSetStagePositions(1+2+8, x, y, z, alpha, beta)
DM.EMWaitUntilReady()
DM.EMStopStage()
```

---

## DM-Script Bridge (for missing Python bindings)

```python
# Execute DM-Script from Python
DM.ExecuteScriptString("""
    number voltage = EMGetHighTension()
    Result("HT = " + voltage + " V\\n")
""")

# Using execdmscript for variable exchange
import execdmscript
result_vars = {"stage_x": float}
execdmscript.exec_dm_script(
    "number stage_x = EMGetStageX()",
    readvars=result_vars
)
print(result_vars["stage_x"])
```

---

## GMS Version Notes

| GMS | Key change |
|---|---|
| 3.60 | Reference version for GMS-MCP |
| 3.5.2 | `UnregisterAllListeners()` added (avoid 3.5.0–3.5.1) |
| 3.4.x | `CreateImage(numpy_array)` introduced; Python 3.7 embedded |
| < 3.4 | Python unavailable — DM-Script only |

**Critical memory rule**: `img.GetNumArray()` returns a live memory-mapped view.
Never do `arr = new_data`; always use `arr[:] = new_data` for in-place writes.
Delete `Py_Image` variables explicitly or they lock GMS memory until restart.
