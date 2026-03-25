"""
Example 05 — Automated tomographic tilt series.

Demonstrates:
- Moving the stage to the region of interest
- Running a full ±60° tilt series in 2° steps
- Monitoring per-frame intensity for beam-induced damage
- Saving frames to disk

Run:
    GMS_SIMULATE=1 python examples/05_tilt_series.py
"""

import asyncio
import os
import sys

sys.path.insert(0, "src")
os.environ.setdefault("GMS_SIMULATE", "1")

from gms_mcp.client import run_agent


QUERY = """
Run a complete tomographic tilt series workflow:

1. Check the current stage position and microscope state.
2. Move the stage to X = 50 µm, Y = -20 µm (simulate centering on ROI).
3. Acquire a tilt series from -60° to +60° in 2° steps,
   with 0.5 s exposure and 2× binning.
4. From the per-tilt statistics, report:
   - Total number of frames acquired
   - Mean electron count averaged across all tilt angles
   - Maximum intensity variation (max - min of per-frame means)
   - Whether the intensity variation exceeds 20% of the mean
     (which would suggest beam-induced damage or sample movement)
5. Return the stage to α = 0° when finished.
"""


async def main():
    result = await run_agent(query=QUERY, model="qwen2.5:7b", verbose=True)
    print("\n─── Agent Response ───")
    print(result["answer"])


if __name__ == "__main__":
    asyncio.run(main())
